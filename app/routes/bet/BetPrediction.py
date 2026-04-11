# backend/app/routes/bet/BetPrediction.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import select
from app.db import get_db
from app.models.bet.BetPrediction import BetPrediction
from app.models.bet.Bet import Bet
from app.models.bet.BetDate import BetDate, bet_date_matches
from app.models.competition.match import Match
from app.schemas.bet.BetPrediction import BetPredictionRead
from app.core.security import get_current_user
from app.models.user.user import User

router = APIRouter(prefix="/predictions", tags=["BetPrediction"])

FINISHED_STATUSES = {"finalizado", "finished"}


def _all_matches_finished(session: Session, bet_date_id: int) -> bool:
    """Retorna True si todos los partidos de la fecha están en estado Finalizado."""
    match_ids = session.execute(
        select(bet_date_matches.c.match_id).where(
            bet_date_matches.c.bet_date_id == bet_date_id
        )
    ).scalars().all()

    if not match_ids:
        return False

    matches = session.execute(
        select(Match.status).where(Match.id.in_(match_ids))
    ).scalars().all()

    return len(matches) > 0 and all(
        str(s).strip().lower() in FINISHED_STATUSES for s in matches
    )


# Listar predicciones de una apuesta.
# Regla de transparencia:
#   - Dueño o admin: siempre pueden ver sus propias predicciones.
#   - Cualquier usuario autenticado: puede ver cuando TODOS los partidos
#     de la fecha estén en estado "Finalizado". Antes de eso, las predicciones
#     son privadas para preservar la integridad del juego.
@router.get("/bet/{bet_id}", response_model=List[BetPredictionRead])
def list_predictions(
    bet_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    bet = session.get(Bet, bet_id)
    if not bet:
        raise HTTPException(status_code=404, detail="Apuesta no encontrada")

    is_owner = bet.user_id == current_user.id
    is_admin = current_user.role.upper() == "ADMIN"

    if not is_owner and not is_admin:
        if not _all_matches_finished(session, bet.bet_date_id):
            raise HTTPException(
                status_code=403,
                detail="Las predicciones solo son visibles cuando todos los partidos de la fecha han finalizado."
            )

    result = session.execute(select(BetPrediction).where(BetPrediction.bet_id == bet_id))
    return result.scalars().all()
