# backend/app/routes/bet/finalize.py
import logging
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks

logger = logging.getLogger(__name__)
from sqlalchemy.orm import Session
from typing import Optional, Dict, Any
from app.db import get_db
from app.core.dependencies import get_current_admin_user
from app.models.user.user import User
from app.models.bet.BetDate import BetDate
from app.models.bet.Bet import Bet
from app.models.bet.UserWallet import UserWallet
from app.schemas.bet.finalize import (
    FinalizeRequest,
    FinalizeResponse,
    WinnerInfo,
    CloseBetDateResponse,
    ReopenBetDateRequest,
    ReopenBetDateResponse,
    FinalizationStats,
    FinalizationSummary,
    FinalizationValidation,
    NotificationData
)
from app.services.transaction_service import TransactionService
from app.constants.bet_constants import MIN_POINTS_TO_WIN
from datetime import datetime, timedelta
from types import SimpleNamespace
import time

router = APIRouter(prefix="/bet-integration", tags=["Bet Finalization"])


@router.post("/finalize/{bet_date_id}", response_model=FinalizeResponse)
def finalize_betdate(
    bet_date_id: int,
    request: Optional[FinalizeRequest] = None,
    background_tasks: BackgroundTasks = None,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Finalizar una fecha de pronósticos y distribuir premios
    """
    start_time = time.time()
    
    # Configuración por defecto
    if request is None:
        request = FinalizeRequest()
    
    if background_tasks is None:
        # Para compatibilidad
        class DummyBackgroundTasks:
            def add_task(self, func, *args, **kwargs):
                pass
        background_tasks = DummyBackgroundTasks()
    
    # 1. Verificar que la fecha exista
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")
    
    # 2. Verificar que no esté ya finalizada
    if betdate.status == "finished":
        raise HTTPException(status_code=400, detail="Esta fecha ya está finalizada")
    
    # 3. Verificar que todos los partidos hayan finalizado (a menos que force=True)
    if not request.force:
        pending_matches = [m for m in betdate.matches if m.status != "Finalizado"]
        if pending_matches:
            raise HTTPException(
                status_code=400, 
                detail=f"No se puede finalizar: {len(pending_matches)} partidos pendientes. Use force=true para forzar."
            )
    
    try:
        # 4. Primero generar el ranking para tener datos actualizados
        from .ranking import get_betdate_ranking
        try:
            ranking_response = get_betdate_ranking(bet_date_id, session)
            ranking_data = ranking_response.data
        except HTTPException as e:
            if e.status_code == 404 and "No hay pronósticos" in str(e.detail):
                ranking_data = SimpleNamespace(
                    qualifies_for_prize=False,
                    ranking=[]
                )
            else:
                raise
        
        # 5. Verificar si hay ganador (≥13 puntos)
        # Incluir carryover de fechas anteriores sin liquidar
        carryover_betdates = (
            session.query(BetDate)
            .filter(BetDate.id < betdate.id)
            .filter((BetDate.prize_cop > 0) | (BetDate.accumulated_prize > 0))
            .all()
        )
        carryover_total = sum(b.prize_cop + b.accumulated_prize for b in carryover_betdates)
        total_prize = betdate.prize_cop + betdate.accumulated_prize + carryover_total
        qualifies_for_prize = ranking_data.qualifies_for_prize
        
        winner_info = None
        winners_info = None
        prize_distributed = 0
        prize_accumulated = 0
        
        if qualifies_for_prize and ranking_data.ranking and request.distribute_prize:
            # HAY GANADOR(ES) - Distribuir premio
            top_points = ranking_data.ranking[0].points
            winners = [r for r in ranking_data.ranking if r.points == top_points]
            
            if len(winners) == 1:
                winner = winners[0]
                
                # Registrar transacción de premio
                TransactionService.award_prize(
                    session=session,
                    user_id=winner.user_id,
                    bet_date_id=betdate.id,
                    prize_amount=total_prize,
                    bet_id=winner.bet_id
                )
                
                prize_distributed = total_prize
                
                # Resetear premios (incluyendo carryover)
                betdate.prize_cop = 0
                betdate.accumulated_prize = 0
                for b in carryover_betdates:
                    b.prize_cop = 0
                    b.accumulated_prize = 0
                
                # Crear info del ganador
                winner_info = WinnerInfo(
                    user_id=winner.user_id,
                    username=winner.username,
                    points=winner.points,
                    correct_picks=winner.correct_picks,
                    bet_id=winner.bet_id,
                    submitted_at=winner.submitted_at,
                    prize_amount=total_prize
                )
                
                message = f"¡{winner.username} ha ganado el premio de ${total_prize:,} COP!"
            else:
                base_amount = total_prize // len(winners)
                remainder = total_prize % len(winners)
                
                winners_info = []
                for idx, winner in enumerate(winners):
                    prize_amount = base_amount + (1 if idx < remainder else 0)
                    TransactionService.award_prize(
                        session=session,
                        user_id=winner.user_id,
                        bet_date_id=betdate.id,
                        prize_amount=prize_amount,
                        bet_id=winner.bet_id
                    )
                    winners_info.append(WinnerInfo(
                        user_id=winner.user_id,
                        username=winner.username,
                        points=winner.points,
                        correct_picks=winner.correct_picks,
                        bet_id=winner.bet_id,
                        submitted_at=winner.submitted_at,
                        prize_amount=prize_amount
                    ))
                
                prize_distributed = total_prize
                prize_accumulated = 0
                
                # Resetear premios (incluyendo carryover)
                betdate.prize_cop = 0
                betdate.accumulated_prize = 0
                for b in carryover_betdates:
                    b.prize_cop = 0
                    b.accumulated_prize = 0
                
                winner_info = winners_info[0]
                usernames = ", ".join([w.username for w in winners])
                message = (
                    f"¡Empate entre {usernames}! Premio dividido en partes iguales."
                )
            
        else:
            # NO HAY GANADOR - Acumular premio
            # Consolidar premio total como acumulado para la próxima fecha
            betdate.accumulated_prize = total_prize
            betdate.prize_cop = 0
            for b in carryover_betdates:
                b.prize_cop = 0
                b.accumulated_prize = 0
            
            prize_distributed = 0
            prize_accumulated = betdate.accumulated_prize
            
            if ranking_data.ranking:
                top_user = ranking_data.ranking[0]
                message = f"Ningún usuario alcanzó {MIN_POINTS_TO_WIN} puntos. Máximo: {top_user.points} puntos por {top_user.username}. Premio acumulado: ${prize_accumulated:,} COP"
            else:
                message = f"Ningún usuario alcanzó {MIN_POINTS_TO_WIN} puntos. Premio acumulado."
        
        # 6. Actualizar estado de la fecha
        betdate.status = "finished"
        
        # 7. Guardar cambios
        session.commit()
        
        # 8. Enviar notificaciones en background
        if request.notify_users:
            background_tasks.add_task(
                send_finalization_notifications,
                betdate.id,
                qualifies_for_prize,
                [w.dict() for w in winners_info] if winners_info else (winner_info.dict() if winner_info else None),
                ranking_data.ranking[:10] if ranking_data.ranking else []
            )
        
        # 9. Calcular tiempo de procesamiento
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        return FinalizeResponse(
            success=True,
            message=message,
            betdate_id=betdate.id,
            betdate_name=betdate.name,
            status=betdate.status,
            qualified_for_prize=qualifies_for_prize,
            winner_info=winner_info,
            winners_info=winners_info,
            prize_distributed=prize_distributed,
            prize_accumulated=prize_accumulated,
            next_betdate_prize=betdate.accumulated_prize,
            ranking_generated=True,
            total_participants=len(ranking_data.ranking) if ranking_data.ranking else 0,
            processed_at=datetime.now()
        )
        
    except Exception as e:
        session.rollback()
        logger.error(f"finalize_betdate failed: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail="Error interno al finalizar la fecha")


@router.post("/close/{bet_date_id}", response_model=CloseBetDateResponse)
def close_betdate(
    bet_date_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Cerrar fecha de pronósticos (solo cambiar estado)
    """
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")
    
    if betdate.status == "closed":
        raise HTTPException(status_code=400, detail="La fecha ya está cerrada")
    
    if betdate.status == "finished":
        raise HTTPException(status_code=400, detail="No se puede cerrar una fecha finalizada")
    
    betdate.status = "closed"
    session.commit()
    
    # Calcular si se puede reabrir (si aún no pasó la fecha de cierre)
    now = datetime.now()
    can_reopen = now < betdate.close_datetime
    
    # Calcular tiempo restante
    remaining_time = None
    if can_reopen and betdate.close_datetime:
        diff = betdate.close_datetime - now
        hours = diff.seconds // 3600
        minutes = (diff.seconds % 3600) // 60
        remaining_time = f"{hours}h {minutes}m"
    
    return CloseBetDateResponse(
        message=f"Fecha '{betdate.name}' cerrada exitosamente",
        betdate_id=betdate.id,
        betdate_name=betdate.name,
        status=betdate.status,
        closed_at=datetime.now(),
        can_reopen=can_reopen,
        remaining_time=remaining_time
    )


@router.post("/reopen/{bet_date_id}", response_model=ReopenBetDateResponse)
def reopen_betdate(
    bet_date_id: int,
    request: ReopenBetDateRequest,
    admin_user: User = Depends(get_current_admin_user),
    session: Session = Depends(get_db)
):
    """
    Reabrir una fecha de pronósticos cerrada
    """
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")
    
    if betdate.status != "closed":
        raise HTTPException(
            status_code=400, 
            detail=f"No se puede reabrir una fecha con estado '{betdate.status}'"
        )
    
    # Verificar que no haya pasado la fecha de cierre original
    now = datetime.now()
    if now > betdate.close_datetime:
        # Extender fecha de cierre si se solicita
        if request.extend_close_time:
            new_close_datetime = now + timedelta(hours=request.extend_close_time)
            betdate.close_datetime = new_close_datetime
        else:
            raise HTTPException(
                status_code=400, 
                detail="La fecha de cierre ya pasó. Especifique extend_close_time para extenderla."
            )
    
    # Reabrir fecha
    betdate.status = "open"
    session.commit()
    
    return ReopenBetDateResponse(
        message=f"Fecha '{betdate.name}' reabierta exitosamente",
        betdate_id=betdate.id,
        betdate_name=betdate.name,
        status=betdate.status,
        new_close_datetime=betdate.close_datetime if request.extend_close_time else None,
        reopened_at=datetime.now(),
        reason=request.reason
    )


@router.get("/validate/{bet_date_id}", response_model=FinalizationValidation)
def validate_finalization(
    bet_date_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Validar si se puede finalizar una fecha
    """
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")
    
    reasons = []
    recommendations = []
    
    # Verificar estado actual
    if betdate.status == "finished":
        reasons.append("La fecha ya está finalizada")
        can_finalize = False
    elif betdate.status == "closed":
        reasons.append("La fecha está cerrada")
        can_finalize = False
    else:
        can_finalize = True
    
    # Verificar partidos pendientes
    pending_matches = [m for m in betdate.matches if m.status != "Finalizado"]
    pending_matches_details = []
    
    for match in pending_matches[:5]:  # Limitar a 5 partidos para la respuesta
        pending_matches_details.append({
            "match_id": match.id,
            "home_team": match.home_team.name if match.home_team else "Desconocido",
            "away_team": match.away_team.name if match.away_team else "Desconocido",
            "match_date": match.match_date.isoformat() if match.match_date else None,
            "status": match.status
        })
    
    if pending_matches:
        reasons.append(f"{len(pending_matches)} partidos pendientes")
        recommendations.append("Use force=true para finalizar de todos modos")
        recommendations.append("Espere a que todos los partidos finalicen")
    
    # Verificar si hay pronósticos
    total_bets = session.query(Bet).filter_by(bet_date_id=bet_date_id).count()
    if total_bets == 0:
        reasons.append("No hay pronósticos en esta fecha")
        recommendations.append("Considere cancelar la fecha en lugar de finalizar")
    
    # Calcular premio
    prize_pool = betdate.prize_cop + betdate.accumulated_prize
    
    # Estimación de tiempo de procesamiento
    estimated_time = "1-2 segundos"
    if total_bets > 50:
        estimated_time = "3-5 segundos"
    elif total_bets > 100:
        estimated_time = "5-10 segundos"
    
    return FinalizationValidation(
        can_finalize=can_finalize and len(pending_matches) == 0,
        reasons=reasons,
        pending_matches=len(pending_matches),
        pending_matches_details=pending_matches_details,
        total_bets=total_bets,
        prize_pool=prize_pool,
        estimated_processing_time=estimated_time,
        recommendations=recommendations
    )


@router.get("/summary/{bet_date_id}", response_model=FinalizationSummary)
def get_finalization_summary(
    bet_date_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Obtener resumen completo de finalización
    """
    # Primero finalizar para tener datos actualizados
    try:
        finalize_response = finalize_betdate(bet_date_id, session=session)
    except HTTPException as e:
        if e.status_code != 400:  # Si no es porque ya está finalizada
            raise e
        # Si ya está finalizada, obtener datos actuales
        finalize_response_data = {
            "success": True,
            "message": "Fecha ya finalizada",
            "betdate_id": bet_date_id,
            "betdate_name": "",
            "status": "finished",
            "qualified_for_prize": False,
            "ranking_generated": True,
            "total_participants": 0,
            "processed_at": datetime.now()
        }
        finalize_response = FinalizeResponse(**finalize_response_data)
    
    # Obtener estadísticas
    bets = session.query(Bet).filter_by(bet_date_id=bet_date_id).all()
    total_bets = len(bets)
    
    if bets:
        points = [bet.points for bet in bets]
        average_points = sum(points) / len(points)
        max_points = max(points)
        min_points = min(points)
        
        # Contar aciertos
        total_correct_picks = 0

        for bet in bets:
            for prediction in bet.predictions:
                if prediction.points > 0:
                    total_correct_picks += 1

        users_above_13 = len([bet for bet in bets if bet.points >= MIN_POINTS_TO_WIN])
    else:
        average_points = max_points = min_points = 0
        total_correct_picks = users_above_13 = 0
    
    # Obtener premios
    betdate = session.query(BetDate).get(bet_date_id)
    prize_pool_before = betdate.prize_cop + betdate.accumulated_prize if betdate else 0
    prize_pool_after = betdate.accumulated_prize if betdate else 0  # Después de finalizar
    
    stats = FinalizationStats(
        betdate_id=bet_date_id,
        total_bets=total_bets,
        total_participants=len(set([bet.user_id for bet in bets])),
        average_points=average_points,
        max_points=max_points,
        min_points=min_points,
        users_above_13=users_above_13,
        total_correct_picks=total_correct_picks,
        prize_pool_before=prize_pool_before,
        prize_pool_after=prize_pool_after,
        processing_time_ms=0
    )
    
    # Obtener top 3 del ranking
    from .ranking import get_betdate_ranking
    try:
        ranking_response = get_betdate_ranking(bet_date_id, session)
        ranking_top_3 = [
            {
                "position": entry.position,
                "username": entry.username,
                "points": entry.points,
                "correct_picks": entry.correct_picks,
            }
            for entry in ranking_response.data.ranking[:3]
        ]
    except Exception:
        ranking_top_3 = []
    
    # Resumen de partidos
    if betdate and betdate.matches:
        matches_summary = {
            "total_matches": len(betdate.matches),
            "finished_matches": len([m for m in betdate.matches if m.status == "Finalizado"]),
            "pending_matches": len([m for m in betdate.matches if m.status != "Finalizado"]),
            "first_match": min([m.match_date for m in betdate.matches]).isoformat() if betdate.matches else None,
            "last_match": max([m.match_date for m in betdate.matches]).isoformat() if betdate.matches else None
        }
    else:
        matches_summary = {}
    
    return FinalizationSummary(
        finalize_response=finalize_response,
        stats=stats,
        ranking_top_3=ranking_top_3,
        matches_summary=matches_summary
    )


def send_finalization_notifications(
    betdate_id: int, 
    has_winner: bool, 
    winner_info: Optional[Any] = None,
    top_10_ranking: list = None
):
    """
    Función de background para enviar notificaciones
    """
    # Implementar notificaciones por email, push, etc.
    # Esto se ejecuta en background y no bloquea la respuesta
    
    # Ejemplo de implementación básica:
    logger.info(f"[BACKGROUND] Enviando notificaciones para fecha {betdate_id}")
    if has_winner and winner_info:
        if isinstance(winner_info, list):
            logger.info(f"[BACKGROUND] Empate — {len(winner_info)} ganador(es) en fecha {betdate_id}")
        else:
            logger.info(f"[BACKGROUND] Ganador en fecha {betdate_id}")
    if top_10_ranking:
        logger.info(f"[BACKGROUND] Fecha {betdate_id} finalizada — {len(top_10_ranking)} participantes")
