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


# Listar predicciones de una apuesta.
# Cualquier usuario autenticado puede ver las predicciones de cualquier apuesta.
# El ranking ya expone públicamente quién apostó qué puntaje, así que no hay
# información estratégica que proteger aquí.
@router.get("/bet/{bet_id}", response_model=List[BetPredictionRead])
def list_predictions(
    bet_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    bet = session.get(Bet, bet_id)
    if not bet:
        raise HTTPException(status_code=404, detail="Apuesta no encontrada")

    result = session.execute(select(BetPrediction).where(BetPrediction.bet_id == bet_id))
    return result.scalars().all()
