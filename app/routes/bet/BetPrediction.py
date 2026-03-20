# backend/app/routes/bet/BetPrediction.py
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import select
from app.db import get_db
from app.models.bet.BetPrediction import BetPrediction
from app.schemas.bet.BetPrediction import BetPredictionRead

router = APIRouter(prefix="/predictions", tags=["BetPrediction"])

# Listar predicciones de una apuesta
@router.get("/bet/{bet_id}", response_model=List[BetPredictionRead])
def list_predictions(bet_id: int, session: Session = Depends(get_db)):
    result = session.execute(select(BetPrediction).where(BetPrediction.bet_id == bet_id))
    return result.scalars().all()
