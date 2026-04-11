# backend/app/routes/bet/BetPrediction.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import select
from app.db import get_db
from app.models.bet.BetPrediction import BetPrediction
from app.models.bet.Bet import Bet
from app.models.bet.BetDate import BetDate
from app.schemas.bet.BetPrediction import BetPredictionRead
from app.core.security import get_current_user
from app.models.user.user import User

router = APIRouter(prefix="/predictions", tags=["BetPrediction"])


# Listar predicciones de una apuesta.
# - Dueño o admin: siempre pueden ver.
# - Cualquier usuario autenticado: puede ver si la fecha ya está finalizada
#   (el ranking es público, mostrar predicciones no revela info estratégica).
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
        # Permitir si la fecha está finalizada (el ranking ya es público)
        bet_date = session.get(BetDate, bet.bet_date_id)
        date_finished = bet_date and str(bet_date.status).lower() in ("finished", "finalizada", "finalizado")
        if not date_finished:
            raise HTTPException(status_code=403, detail="No tienes permiso para ver estas predicciones")

    result = session.execute(select(BetPrediction).where(BetPrediction.bet_id == bet_id))
    return result.scalars().all()
