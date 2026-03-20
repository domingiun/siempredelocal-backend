# backend/app/routes/bet/Bet.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from app.db import get_db
from app.models.bet.Bet import Bet
from app.schemas.bet.Bet import BetCreate, BetRead
from app.models.bet.BetPrediction import BetPrediction

router = APIRouter(prefix="/bets", tags=["Bets"])

# Enviar apuesta
@router.post("/", response_model=BetRead)
def create_bet(
    bet_in: BetCreate,
    user_id: int,
    session: Session = Depends(get_db)
):
    # 1. Evitar doble apuesta
    existing = session.query(Bet).filter_by(
        user_id=user_id,
        bet_date_id=bet_in.bet_date_id
    ).first()

    if existing:
        raise HTTPException(400, "Ya apostaste en esta fecha")

    # 2. Crear apuesta
    bet = Bet(
        user_id=user_id,
        bet_date_id=bet_in.bet_date_id
    )
    session.add(bet)
    session.flush()  # 👈 NO commit aún

    # 3. Crear predicciones
    for pred in bet_in.predictions:
        session.add(
            BetPrediction(
                bet_id=bet.id,
                match_id=pred.match_id,
                predicted_home_score=pred.predicted_home_score,
                predicted_away_score=pred.predicted_away_score
            )
        )

    # 4. Commit final
    session.commit()
    session.refresh(bet)

    return bet


# Listar pronósticos de un usuario
@router.get("/user/{user_id}", response_model=List[BetRead])
def list_user_bets(user_id: int, session: Session = Depends(get_db)):
    bets = session.execute(select(Bet).where(Bet.user_id == user_id)).scalars().all()
    return bets
