# backend/app/routes/bet/Bet.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from app.db import get_db
from app.models.bet.Bet import Bet
from app.schemas.bet.Bet import BetCreate, BetRead
from app.models.bet.BetPrediction import BetPrediction
from app.core.security import get_current_user
from app.models.user.user import User

router = APIRouter(prefix="/bets", tags=["Bets"])


# Enviar apuesta — user_id se extrae del JWT, no del request
@router.post("/", response_model=BetRead)
def create_bet(
    bet_in: BetCreate,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # 1. Evitar doble apuesta
    existing = session.query(Bet).filter_by(
        user_id=current_user.id,
        bet_date_id=bet_in.bet_date_id
    ).first()

    if existing:
        raise HTTPException(400, "Ya apostaste en esta fecha")

    # 2. Crear apuesta
    bet = Bet(
        user_id=current_user.id,
        bet_date_id=bet_in.bet_date_id
    )
    session.add(bet)
    session.flush()

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


# Listar pronósticos — solo el propio usuario o admin
@router.get("/user/{user_id}", response_model=List[BetRead])
def list_user_bets(
    user_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    if current_user.id != user_id and current_user.role.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver estas apuestas")

    bets = session.execute(select(Bet).where(Bet.user_id == user_id)).scalars().all()
    return bets
