# backend/app/routes/bet/BetPrediction.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import select
from app.db import get_db
from app.models.bet.BetPrediction import BetPrediction
from app.models.bet.Bet import Bet
from app.schemas.bet.BetPrediction import BetPredictionRead
from app.core.security import get_current_user
from app.models.user.user import User

router = APIRouter(prefix="/predictions", tags=["BetPrediction"])


# Listar predicciones de una apuesta — solo el dueño o admin
@router.get("/bet/{bet_id}", response_model=List[BetPredictionRead])
def list_predictions(
    bet_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    bet = session.get(Bet, bet_id)
    if not bet:
        raise HTTPException(status_code=404, detail="Apuesta no encontrada")

    if bet.user_id != current_user.id and current_user.role.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estas predicciones")

    result = session.execute(select(BetPrediction).where(BetPrediction.bet_id == bet_id))
    return result.scalars().all()
