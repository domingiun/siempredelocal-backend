# backend/app/routes/bet/integration.py
import logging
from fastapi import APIRouter, Depends, HTTPException, Request
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy.orm import Session
from sqlalchemy import text, func
from typing import List, Optional

logger = logging.getLogger(__name__)
limiter = Limiter(key_func=get_remote_address)
from datetime import timedelta
from app.db import get_db
from app.core.security import get_current_user
from app.core.dependencies import get_current_admin_user
from app.models.user.user import User
from app.services.bet_service import BetService
from app.schemas.bet.integration import (
    AvailableMatchesResponse,
    AvailableMatch,
    CreateBetDateRequest,
    BetDateCreatedResponse,
    PredictionRequest,
    PlaceBetRequest,
    PlaceBetResponse,
    BetDateWithMatches,
    MatchInBetDate,
    MatchFilter,
    BetValidationRequest,
    BetValidationResponse,
    IntegrationStats,
    UserBettingStatus
)
from app.services.transaction_service import TransactionService
from app.models.competition.match import Match
from app.models.bet.BetDate import BetDate
from app.models.bet.Bet import Bet
from app.models.bet.BetPrediction import BetPrediction
from app.models.bet.UserWallet import UserWallet
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from datetime import datetime
from typing import Dict, Any


router = APIRouter(prefix="/bet-integration", tags=["Bet Integration"])


@router.get("/available-matches", response_model=AvailableMatchesResponse)
def get_available_matches(
    competition_id: Optional[int] = None,
    session: Session = Depends(get_db)
):
    """
    Obtener partidos disponibles para crear fecha de pronósticos
    
    - **competition_id**: Filtrar por competencia específica
    - Retorna solo partidos programados que no estén en fechas activas
    """
    try:
        matches = BetService.get_available_matches_for_betdate(
            session, competition_id
        )
        
        # Convertir a schema AvailableMatch
        available_matches = []
        for match in matches:
            available_matches.append(AvailableMatch(
                id=match.id,
                home_team=match.home_team.name if match.home_team else "",
                away_team=match.away_team.name if match.away_team else "",
                match_date=match.match_date,
                competition=match.competition.name if match.competition else None,
                stadium=match.stadium,
                competition_id=match.competition_id,
                round_name=match.round.name if match.round else None
            ))
        
        return AvailableMatchesResponse(
            matches=available_matches,
            total_count=len(available_matches),
            competition_id=competition_id,
            available_for_betdate=len(available_matches) >= 10
        )
        
    except Exception as e:
        logger.error(f"get_available_matches failed: {e}", exc_info=True)
        raise HTTPException(
            status_code=500,
            detail="No se pudieron obtener los partidos disponibles"
        )


@router.post("/create-betdate", response_model=BetDateCreatedResponse)
def create_betdate(
    request: CreateBetDateRequest,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Crear una nueva fecha de pronósticos (solo administradores)
    
    - **name**: Nombre descriptivo de la fecha
    - **start_datetime**: Fecha/hora de inicio
    - **match_ids**: Lista de EXACTAMENTE 10 IDs de partidos
    - **prize_cop**: Premio inicial (opcional)
    - **required_credits**: Créditos requeridos (default: 1)
    """
    try:
        betdate = BetService.create_betdate_with_matches(
            session=session,
            name=request.name,
            start_datetime=request.start_datetime,
            match_ids=request.match_ids,
            prize_cop=request.prize_cop
        )
        
        # Calcular contribución estimada (asumiendo 20 pronósticos máximos)
        estimated_contribution = 1950 * request.required_credits * 20
        
        return BetDateCreatedResponse(
            id=betdate.id,
            name=betdate.name,
            start_datetime=betdate.start_datetime,
            close_datetime=betdate.close_datetime,
            status=betdate.status,
            prize_cop=betdate.prize_cop,
            match_count=len(betdate.matches),
            required_credits=betdate.required_credits,
            estimated_prize_contribution=estimated_contribution
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        logger.error(f"create_betdate failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al crear fecha de pronósticos")


@router.post("/place-bet", response_model=PlaceBetResponse)
@limiter.limit("10/minute")
def place_bet(
    request: Request,
    body: PlaceBetRequest,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Colocar una apuesta en una fecha disponible

    - **bet_date_id**: ID de la fecha de pronósticos
    - **predictions**: Lista de 10 predicciones con marcadores
    """
    user_id = current_user.id
    try:
        # 1. Verificar que la fecha de pronósticos exista y esté abierta
        betdate = session.query(BetDate).get(body.bet_date_id)
        if not betdate:
            raise ValueError("Fecha de pronósticos no encontrada")

        # Verificar estado y fecha de cierre real (recalcular por seguridad)
        if BetService.update_betdate_status(session, betdate):
            session.commit()
            session.refresh(betdate)

        if betdate.status != "open":
            raise ValueError(f"Las pronósticos para esta fecha están {betdate.status}")

        now = datetime.utcnow()
        close_dt = betdate.close_datetime
        if close_dt is None and betdate.matches:
            match_dates = [m.match_date for m in betdate.matches if m.match_date]
            if match_dates:
                close_dt = min(match_dates) - timedelta(hours=1)
        if close_dt and now > close_dt:
            betdate.status = "closed"
            betdate.close_datetime = close_dt
            session.commit()
            raise ValueError("Las pronósticos para esta fecha ya cerraron")

        # Los pronósticos son gratuitos — no se descuentan créditos ni se cobra entrada.
        # El premio de cada fecha es fijo (betdate.prize_cop), definido por el admin al crearla.

        # 3. Validar predicciones
        if len(body.predictions) != 10:
            raise ValueError("Debe hacer exactamente 10 predicciones")

        # Verificar que todos los partidos sean de esta fecha
        betdate_match_ids = [m.id for m in betdate.matches]
        for pred in body.predictions:
            if pred.match_id not in betdate_match_ids:
                match_info = session.query(Match).get(pred.match_id)
                if match_info:
                    raise ValueError(f"El partido {match_info.home_team.name} vs {match_info.away_team.name} no pertenece a esta fecha")
                else:
                    raise ValueError(f"El partido ID {pred.match_id} no existe")

        # 5. Crear la apuesta
        bet = Bet(
            user_id=user_id,
            bet_date_id=body.bet_date_id,
            is_finalized=False,
            points=0
        )

        session.add(bet)
        session.flush()  # Para obtener el ID

        # 6. Crear predicciones
        for pred in body.predictions:
            bet_pred = BetPrediction(
                bet_id=bet.id,
                match_id=pred.match_id,
                predicted_home_score=pred.predicted_home_score,
                predicted_away_score=pred.predicted_away_score,
                points=0
            )
            session.add(bet_pred)

        # 7. Commit — sin transacción financiera ni cobro, los pronósticos son gratuitos
        session.commit()
        logger.info("place_bet OK — bet_id=%s user_id=%s", bet.id, user_id)

        # 8. Preparar detalles adicionales
        bet_details = {
            "bet_date_name": betdate.name,
            "close_datetime": betdate.close_datetime.isoformat() if betdate.close_datetime else None,
            "predictions_count": len(body.predictions),
            "first_match_date": min([m.match_date for m in betdate.matches]).isoformat() if betdate.matches else None,
        }

        return PlaceBetResponse(
            success=True,
            message="Pronósticos registrada exitosamente",
            bet_id=bet.id,
            credits_used=0,
            credits_remaining=None,
            prize_contribution=0,
            total_prize=betdate.prize_cop + betdate.accumulated_prize,
            submitted_at=bet.submitted_at.isoformat() if bet.submitted_at else None,
            bet_details=bet_details
        )

    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        logger.error(f"place_bet failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al procesar la apuesta")

@router.get("/betdate/{bet_date_id}", response_model=BetDateWithMatches)
def get_betdate_with_matches(
    bet_date_id: int,
    session: Session = Depends(get_db)
):
    """
    Obtener detalles completos de una fecha de pronósticos incluyendo partidos
    """
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")

    # Persistir estado si corresponde
    if BetService.update_betdate_status(session, betdate):
        session.commit()
        session.refresh(betdate)
    
    # Convertir matches a schema
    match_list = []
    for match in betdate.matches:
        match_list.append(MatchInBetDate(
            id=match.id,
            home_team=match.home_team.name if match.home_team else "",
            away_team=match.away_team.name if match.away_team else "",
            home_team_logo=match.home_team.logo_url if match.home_team else None,
            away_team_logo=match.away_team.logo_url if match.away_team else None,
            match_date=match.match_date,
            stadium=match.stadium,
            status=match.status,
            competition=match.competition.name if match.competition else None
        ))
    
    # Calcular tiempo restante si está abierto
    remaining_time = None
    if betdate.status == "open" and betdate.close_datetime:
        now = datetime.utcnow()
        if now < betdate.close_datetime:
            diff = betdate.close_datetime - now
            hours = diff.seconds // 3600
            minutes = (diff.seconds % 3600) // 60
            remaining_time = f"{hours}h {minutes}m"
    
    # Contar pronósticos
    bet_count_result = session.execute(
    text("SELECT COUNT(*) FROM bets WHERE bet_date_id = :bet_date_id"),
        {"bet_date_id": bet_date_id}
    ).scalar()
    bet_count = bet_count_result if bet_count_result else 0
    
    close_dt = betdate.close_datetime
    is_open = betdate.status == "open" and close_dt is not None and datetime.utcnow() <= close_dt

    return BetDateWithMatches(
        id=betdate.id,
        name=betdate.name,
        start_datetime=betdate.start_datetime,
        close_datetime=betdate.close_datetime,
        status=betdate.status,
        prize_cop=betdate.prize_cop,
        accumulated_prize=betdate.accumulated_prize,
        total_prize=betdate.prize_cop + betdate.accumulated_prize,
        required_credits=betdate.required_credits,
        is_betting_open=is_open,
        matches=match_list,
        bet_count=bet_count,
        remaining_time=remaining_time
    )


@router.post("/validate-bet", response_model=BetValidationResponse)
def validate_bet(
    request: BetValidationRequest,
    session: Session = Depends(get_db)
):
    """
    Validar una apuesta antes de enviarla
    """
    errors = []
    warnings = []
    
    # Verificar fecha
    betdate = session.query(BetDate).get(request.bet_date_id)
    if not betdate:
        errors.append("Fecha de pronósticos no encontrada")
        return BetValidationResponse(
            valid=False,
            message="Fecha no encontrada",
            errors=errors,
            warnings=warnings,
            required_credits=1,
            user_has_credits=False,
            betdate_is_open=False,
            has_previous_bet=False
        )
    
    # Verificar estado
    betdate_is_open = (
        betdate.status == "open"
        and betdate.close_datetime is not None
        and datetime.utcnow() <= betdate.close_datetime
    )
    
    # Verificar créditos del usuario
    wallet = session.query(UserWallet).filter_by(user_id=request.user_id).first()
    user_has_credits = wallet and wallet.credits >= betdate.required_credits
    
    # Verificar si ya apostó
    has_previous_bet = session.query(Bet).filter_by(
        user_id=request.user_id,
        bet_date_id=request.bet_date_id
    ).first() is not None
    
    # Verificar predicciones
    if len(request.predictions) != 10:
        errors.append("Debe hacer exactamente 10 predicciones")
    
    # Verificar partidos de la fecha
    if betdate:
        betdate_match_ids = [m.id for m in betdate.matches]
        for pred in request.predictions:
            if pred.match_id not in betdate_match_ids:
                errors.append(f"El partido ID {pred.match_id} no pertenece a esta fecha")
    
    # Advertencias por marcadores extremos
    for pred in request.predictions:
        if pred.predicted_home_score > 5 or pred.predicted_away_score > 5:
            warnings.append(f"Marcador alto en partido {pred.match_id}")
    
    valid = len(errors) == 0 and betdate_is_open and user_has_credits
    
    return BetValidationResponse(
        valid=valid,
        message="Validación completada" if valid else "Hay errores en la validación",
        errors=errors,
        warnings=warnings,
        estimated_points=None,  # Podría calcularse con estadísticas
        required_credits=betdate.required_credits if betdate else 1,
        user_has_credits=user_has_credits,
        betdate_is_open=betdate_is_open,
        has_previous_bet=has_previous_bet
    )


@router.get("/stats", response_model=IntegrationStats)
def get_integration_stats(session: Session = Depends(get_db)):
    """
    Obtener estadísticas del sistema de pronósticos
    """
    total_betdates = session.query(BetDate).count()
    active_betdates = session.query(BetDate).filter(
        BetDate.status == "open"
    ).count()
    completed_betdates = session.query(BetDate).filter(
        BetDate.status == "finished"
    ).count()
    
    total_bets = session.query(Bet).count()
    total_users = session.query(User).count()

    # Calcular premio total
    betdates = session.query(BetDate).all()
    total_prize_pool = sum(bd.prize_cop + bd.accumulated_prize for bd in betdates)

    # Promedio de pronósticos por fecha
    average_bets_per_date = total_bets / total_betdates if total_betdates > 0 else 0

    # Competencia más popular (simplificado)
    most_popular_competition = None

    return IntegrationStats(
        total_betdates=total_betdates,
        active_betdates=active_betdates,
        completed_betdates=completed_betdates,
        total_bets=total_bets,
        total_prize_pool=total_prize_pool,
        average_bets_per_date=average_bets_per_date,
        most_popular_competition=most_popular_competition,
        total_users=total_users,
    )


@router.get("/user-status/{user_id}", response_model=UserBettingStatus)
def get_user_betting_status(
    user_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id and current_user.role.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este estado")
    """
    Obtener estado de pronósticos de un usuario
    """
    # Obtener pronósticos del usuario
    user_bets = session.query(Bet).filter_by(user_id=user_id).all()
    
    total_bets = len(user_bets)
    total_points = sum(bet.points for bet in user_bets)
    average_points = total_points / total_bets if total_bets > 0 else 0
    
    # Contar "victorias" (pronósticos con puntos >= 13)
    wins = len([bet for bet in user_bets if bet.points >= 13])
    
    # Total de premios ganados (sumatoria de transacciones PRIZE_WIN completadas)
    total_prizes_won = (
        session.query(func.coalesce(func.sum(Transaction.amount_cop), 0))
        .filter(
            Transaction.user_id == user_id,
            Transaction.transaction_type == TransactionType.PRIZE_WIN,
            Transaction.status == TransactionStatus.COMPLETED,
        )
        .scalar()
        or 0
    )
    
    # Mi Cuenta
    wallet = session.query(UserWallet).filter_by(user_id=user_id).first()
    credits_available = wallet.credits if wallet else 0
    balance_cop = wallet.balance_cop if wallet else 0
    
    # Fechas activas donde puede apostar
    active_betdates = []
    open_betdates = session.query(BetDate).filter(
        BetDate.status == "open"
    ).all()
    
    for betdate in open_betdates:
        # Verificar si ya apostó
        existing_bet = session.query(Bet).filter_by(
            user_id=user_id,
            bet_date_id=betdate.id
        ).first()
        
        # Verificar si tiene créditos
        has_credits = wallet and wallet.credits >= betdate.required_credits
        
        if not existing_bet and has_credits and datetime.utcnow() <= betdate.close_datetime:
            active_betdates.append(betdate.id)
    
    return UserBettingStatus(
        user_id=user_id,
        total_bets=total_bets,
        total_points=total_points,
        average_points=average_points,
        wins=wins,
        total_prizes_won=total_prizes_won,
        credits_available=credits_available,
        balance_cop=balance_cop,
        active_betdates=active_betdates
    )


@router.get("/betdate/{betdate_id}/community")
def get_community_predictions(
    betdate_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Pronósticos de todos los participantes de una fecha.
    Solo disponible cuando la fecha está cerrada o finalizada (no abierta).
    """
    betdate = session.query(BetDate).filter(BetDate.id == betdate_id).first()
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha no encontrada")

    if betdate.status == "open":
        raise HTTPException(
            status_code=403,
            detail="Los pronósticos de otros participantes solo son visibles después de que la fecha cierra"
        )

    bets = (
        session.query(Bet)
        .filter(Bet.bet_date_id == betdate_id)
        .all()
    )

    participants = []
    for bet in bets:
        user = session.query(User).filter(User.id == bet.user_id).first()
        predictions = []
        for pred in bet.predictions:
            match = pred.match
            if not match:
                continue
            home_name = match.home_team.name if match.home_team else f"Equipo {match.home_team_id}"
            away_name = match.away_team.name if match.away_team else f"Equipo {match.away_team_id}"
            home_logo = match.home_team.logo_url if match.home_team else None
            away_logo = match.away_team.logo_url if match.away_team else None
            predictions.append({
                "match_id": pred.match_id,
                "home_team": home_name,
                "away_team": away_name,
                "home_logo": home_logo,
                "away_logo": away_logo,
                "predicted_home": pred.predicted_home_score,
                "predicted_away": pred.predicted_away_score,
                "actual_home": match.home_score,
                "actual_away": match.away_score,
                "match_status": match.status,
                "points": pred.points,
            })
        participants.append({
            "bet_id": bet.id,
            "user_id": bet.user_id,
            "username": user.username if user else f"Usuario {bet.user_id}",
            "avatar_url": user.avatar_url if user else None,
            "total_points": bet.points or 0,
            "rank": bet.rank,
            "predictions": predictions,
        })

    participants.sort(key=lambda x: x["total_points"], reverse=True)

    return {
        "betdate_id": betdate_id,
        "betdate_name": betdate.name,
        "betdate_status": betdate.status,
        "total_participants": len(participants),
        "participants": participants,
    }



@router.get("/me/bets")
def get_my_bets_enriched(
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Devuelve todas las apuestas del usuario con match y betdate ya incluidos.
    Reemplaza N+1 requests de /bets/user/{id} + /matches/{id} + /betdate/{id}.
    """
    bets = session.query(Bet).filter_by(user_id=current_user.id).all()

    result = []
    for bet in bets:
        betdate = bet.bet_date
        predictions = []
        for pred in bet.predictions:
            match = pred.match
            if not match:
                continue
            home_team = match.home_team
            away_team = match.away_team
            competition = match.competition
            predictions.append({
                "id": pred.id,
                "match_id": pred.match_id,
                "predicted_home_score": pred.predicted_home_score,
                "predicted_away_score": pred.predicted_away_score,
                "points": pred.points,
                "match": {
                    "id": match.id,
                    "status": match.status,
                    "match_date": match.match_date.isoformat() if match.match_date else None,
                    "home_score": match.home_score,
                    "away_score": match.away_score,
                    "stadium": match.stadium,
                    "home_team": {"name": home_team.name, "logo_url": home_team.logo_url} if home_team else None,
                    "away_team": {"name": away_team.name, "logo_url": away_team.logo_url} if away_team else None,
                    "competition": competition.name if competition else None,
                },
            })
        result.append({
            "id": bet.id,
            "bet_date_id": bet.bet_date_id,
            "bet_date_name": betdate.name if betdate else f"Fecha #{bet.bet_date_id}",
            "bet_date_status": betdate.status if betdate else None,
            "submitted_at": bet.submitted_at.isoformat() if bet.submitted_at else None,
            "points": bet.points or 0,
            "rank": bet.rank,
            "predictions": predictions,
        })

    result.sort(key=lambda x: x["bet_date_id"], reverse=True)
    return result
