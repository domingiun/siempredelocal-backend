# backend/app/routes/bet/BetDate.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import select, insert
from app.db import get_db
from app.models.bet.BetDate import BetDate, bet_date_matches
from app.models.bet.Bet import Bet
from app.models.competition.match import Match
from app.schemas.bet.BetDate import BetDateCreate, BetDateRead
from app.constants.bet_constants import MAX_BETDATE_MATCHES
from datetime import timedelta
from app.services.bet_service import BetService
from app.core.dependencies import get_current_admin_user
from app.models.user.user import User

router = APIRouter(prefix="/betdates", tags=["BetDate"])


def _betdate_to_read(betdate: BetDate, session: Session) -> BetDateRead:
    bet_count = session.query(Bet).filter(Bet.bet_date_id == betdate.id).count()
    match_count = len(betdate.matches) if betdate.matches else 0
    data = BetDateRead.model_validate(betdate)
    data.bet_count = bet_count
    data.match_count = match_count
    data.matches = betdate.matches or []
    return data


# Crear fecha de pronósticos (selección de 10 partidos)
@router.post("/", response_model=BetDateRead)
def create_betdate(
    data: BetDateCreate,
    session: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    if len(data.match_ids) != MAX_BETDATE_MATCHES:
        raise HTTPException(status_code=400, detail=f"Deben ser exactamente {MAX_BETDATE_MATCHES} partidos")

    matches = session.query(Match).filter(Match.id.in_(data.match_ids)).all()
    if len(matches) != MAX_BETDATE_MATCHES:
        raise HTTPException(status_code=400, detail="Uno o más partidos no existen")

    close_datetime = data.close_datetime
    if not close_datetime:
        match_times = [m.match_date for m in matches]
        earliest_match = min(match_times)
        close_datetime = earliest_match - timedelta(hours=1)

    betdate = BetDate(
        name=data.name,
        start_datetime=data.start_datetime,
        close_datetime=close_datetime,
        status="open",
        prize_cop=data.prize_cop,
        accumulated_prize=data.accumulated_prize,
        required_credits=data.required_credits,
    )
    session.add(betdate)
    session.flush()

    for match_id in data.match_ids:
        stmt = insert(bet_date_matches).values(bet_date_id=betdate.id, match_id=match_id)
        session.execute(stmt)

    session.commit()
    session.refresh(betdate)
    return _betdate_to_read(betdate, session)


# Obtener detalle de una fecha (incluye matches y bet_count)
@router.get("/{betdate_id}", response_model=BetDateRead)
def get_betdate(betdate_id: int, session: Session = Depends(get_db)):
    betdate = session.get(BetDate, betdate_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="BetDate no encontrada")
    return _betdate_to_read(betdate, session)


@router.put("/{betdate_id}", response_model=BetDateRead)
def update_betdate(
    betdate_id: int,
    data: BetDateCreate,
    session: Session = Depends(get_db),
    _admin: User = Depends(get_current_admin_user),
):
    betdate = session.get(BetDate, betdate_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="BetDate no encontrada")

    # Solo se pueden cambiar partidos si está abierta y sin apuestas
    match_ids_changed = set(data.match_ids) != {m.id for m in (betdate.matches or [])}
    if match_ids_changed:
        if len(data.match_ids) != MAX_BETDATE_MATCHES:
            raise HTTPException(status_code=400, detail=f"Deben ser exactamente {MAX_BETDATE_MATCHES} partidos")
        if betdate.status not in ("open",):
            raise HTTPException(
                status_code=400,
                detail="Solo se pueden cambiar los partidos cuando la fecha está en estado 'open'",
            )
        bet_count = session.query(Bet).filter(Bet.bet_date_id == betdate_id).count()
        if bet_count > 0:
            raise HTTPException(
                status_code=400,
                detail=f"No se pueden cambiar los partidos: ya hay {bet_count} pronóstico(s) registrado(s)",
            )

    betdate.name = data.name
    betdate.start_datetime = data.start_datetime
    betdate.close_datetime = data.close_datetime
    betdate.status = data.status
    betdate.prize_cop = data.prize_cop
    betdate.accumulated_prize = data.accumulated_prize
    betdate.required_credits = data.required_credits

    if match_ids_changed:
        session.execute(
            bet_date_matches.delete().where(bet_date_matches.c.bet_date_id == betdate_id)
        )
        for match_id in data.match_ids:
            session.execute(
                insert(bet_date_matches).values(bet_date_id=betdate_id, match_id=match_id)
            )

    session.commit()
    session.refresh(betdate)
    return _betdate_to_read(betdate, session)


# Listar todas las fechas de pronósticos
@router.get("/", response_model=List[BetDateRead])
def list_betdates(session: Session = Depends(get_db)):
    result = session.execute(select(BetDate))
    betdates = result.scalars().all()
    changed = False
    for betdate in betdates:
        if BetService.update_betdate_status(session, betdate):
            changed = True
    if changed:
        session.commit()
    return [_betdate_to_read(bd, session) for bd in betdates]
