# backend/app/routes/bet/ranking.py
from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.db import get_db
from app.models.bet.BetDate import BetDate
from app.models.bet.Bet import Bet
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from sqlalchemy import func
from app.schemas.bet.ranking import (
    RankingEntryRead as RankingEntry,
    RankingResponse,
)

router = APIRouter(prefix="/bet-integration", tags=["Bet Ranking"])


@router.get("/ranking/{bet_date_id}", response_model=RankingResponse)
def get_betdate_ranking(bet_date_id: int, session: Session = Depends(get_db)):
    """
    Obtener ranking de una fecha de pronósticos.
    Calcula puntos automaticamente si no estan calculados.
    """
    # 1. Verificar que la fecha exista
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")

    # 2. Verificar si todos los partidos han finalizado
    def is_match_finished(status: str) -> bool:
        value = str(status or "").lower().strip()
        return value == "finished" or "finished" in value or "finalizado" in value

    all_matches_finished = True
    for match in betdate.matches:
        if not is_match_finished(match.status):
            all_matches_finished = False
            break

    if not all_matches_finished:
        pending = len([m for m in betdate.matches if not is_match_finished(m.status)])
        raise HTTPException(
            status_code=400,
            detail=f"No se puede generar ranking: {pending} partidos pendientes",
        )

    # 3. Obtener todas las apuestas de esta fecha
    bets = session.query(Bet).filter_by(bet_date_id=bet_date_id).all()
    if not bets:
        raise HTTPException(status_code=404, detail="No hay pronósticos para esta fecha")

    # 4. Calcular puntos para cada apuesta
    ranking_data = []
    for bet in bets:
        total_points = 0
        exact_scores = 0
        correct_winners = 0

        # Calcular puntos para cada prediccion
        for prediction in bet.predictions:
            points = prediction.calculate_match_points()

            # Actualizar puntos en la base de datos
            if prediction.points != points:
                prediction.points = points
                session.add(prediction)

            total_points += points

            # Contar tipos de aciertos
            if points == 3:
                exact_scores += 1
            elif points == 1:
                correct_winners += 1

        # Actualizar puntos totales de la apuesta
        if bet.points != total_points:
            bet.points = total_points
            bet.is_finalized = True
            session.add(bet)

        ranking_data.append(
            {
                "bet": bet,
                "points": total_points,
                "exact_scores": exact_scores,
                "correct_winners": correct_winners,
                "user_id": bet.user_id,
                "username": bet.user.username if bet.user else f"Usuario {bet.user_id}",
                "bet_id": bet.id,
                "submitted_at": bet.submitted_at,
            }
        )

    session.commit()

    # 5. Ordenar ranking (por puntos descendente, luego por tiempo ascendente)
    ranking_data.sort(key=lambda x: (-x["points"], x["submitted_at"]))

    # 6. Preparar respuesta
    ranking_entries = []
    for i, data in enumerate(ranking_data, 1):
        ranking_entries.append(
            RankingEntry(
                user_id=data["user_id"],
                username=data["username"],
                points=data["points"],
                exact_scores=data["exact_scores"],
                correct_winners=data["correct_winners"],
                position=i,
                bet_id=data["bet_id"],
                submitted_at=data["submitted_at"],
            )
        )

    # 7. Verificar si hay ganador (>=13 puntos)
    qualifies_for_prize = False
    if ranking_entries and ranking_entries[0].points >= 13:
        qualifies_for_prize = True

    prize_paid_total = (
        session.query(func.coalesce(func.sum(Transaction.amount_cop), 0))
        .join(Bet, Bet.id == Transaction.reference_id)
        .filter(
            Transaction.transaction_type == TransactionType.PRIZE_WIN,
            Transaction.status == TransactionStatus.COMPLETED,
            Bet.bet_date_id == bet_date_id,
        )
        .scalar()
        or 0
    )

    return RankingResponse(
        success=True,
        message="Ranking generado correctamente",
        data={
            "betdate_id": betdate.id,
            "betdate_name": betdate.name,
            "status": betdate.status,
            "total_prize": betdate.prize_cop + betdate.accumulated_prize,
            "prize_paid_total": int(prize_paid_total),
            "qualifies_for_prize": qualifies_for_prize,
            "ranking": ranking_entries,
            "generated_at": datetime.now(),
        },
    )


@router.get("/ranking-preview/{bet_date_id}")
def get_betdate_ranking_preview(bet_date_id: int, session: Session = Depends(get_db)):
    """
    Vista previa del ranking (solo muestra datos actuales sin calcular).
    """
    betdate = session.query(BetDate).get(bet_date_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")

    bets = session.query(Bet).filter_by(bet_date_id=bet_date_id).all()

    preview_data = []
    for bet in bets:
        preview_data.append(
            {
                "user_id": bet.user_id,
                "username": bet.user.username if bet.user else f"Usuario {bet.user_id}",
                "current_points": bet.points,
                "bet_id": bet.id,
                "submitted_at": bet.submitted_at.isoformat() if bet.submitted_at else None,
                "is_finalized": bet.is_finalized,
            }
        )

    preview_data.sort(key=lambda x: (-x["current_points"], x["submitted_at"]))

    def is_match_finished(status: str) -> bool:
        value = str(status or "").lower().strip()
        return value == "finished" or "finished" in value or "finalizado" in value

    return {
        "betdate_id": betdate.id,
        "betdate_name": betdate.name,
        "status": betdate.status,
        "total_prize": betdate.prize_cop + betdate.accumulated_prize,
        "pending_matches": len([m for m in betdate.matches if not is_match_finished(m.status)]),
        "total_bets": len(bets),
        "ranking_preview": preview_data,
    }
