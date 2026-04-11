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
# Regla de transparencia: cualquier usuario autenticado puede ver las predicciones.
# El frontend ya garantiza que el ranking (y el acceso a predicciones de otros)
# solo se muestra cuando la fecha está finalizada — el backend solo requiere
# que el usuario esté autenticado.
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
