# backend/app/routes/bet/BetDate.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List
from sqlalchemy import select, insert
from app.db import get_db
from app.models.bet.BetDate import BetDate, bet_date_matches
from app.models.competition.match import Match
from app.schemas.bet.BetDate import BetDateCreate, BetDateRead
from datetime import timedelta
from app.services.bet_service import BetService

router = APIRouter(prefix="/betdates", tags=["BetDate"])

# Crear fecha de pronósticos (selección de 10 partidos)
@router.post("/", response_model=BetDateRead)
def create_betdate(data: BetDateCreate, session: Session = Depends(get_db)):
    # Validar que sean exactamente 10 partidos
    if len(data.match_ids) != 10:
        raise HTTPException(
            status_code=400, 
            detail="Deben ser exactamente 10 partidos"
        )
    
    # Verificar que los partidos existan
    matches = session.query(Match).filter(Match.id.in_(data.match_ids)).all()
    if len(matches) != 10:
        raise HTTPException(
            status_code=400, 
            detail="Uno o más partidos no existen"
        )
    
    # Calcular close_datetime automáticamente si no se proporciona
    close_datetime = data.close_datetime
    if not close_datetime:
        # Obtener el partido más temprano
        match_times = [m.match_date for m in matches]
        earliest_match = min(match_times)
        # Cerrar 1 hora antes del primer partido
        close_datetime = earliest_match - timedelta(hours=1)
    
    # Crear BetDate
    betdate = BetDate(
        name=data.name,
        start_datetime=data.start_datetime,
        close_datetime=close_datetime,
        status="open",  # Siempre abierta al crear
        prize_cop=data.prize_cop,
        accumulated_prize=data.accumulated_prize,
        required_credits=data.required_credits
    )
    session.add(betdate)
    session.flush()  # Para obtener el ID sin commit
    
    # Relacionar partidos (tabla asociativa)
    for match_id in data.match_ids:
        stmt = insert(bet_date_matches).values(bet_date_id=betdate.id, match_id=match_id)
        session.execute(stmt)

    session.commit()
    session.refresh(betdate)
    
    # Calcular match_count
    betdate.match_count = len(data.match_ids)

    return BetDateRead.model_validate(betdate)

@router.put("/{betdate_id}", response_model=BetDateRead)
def update_betdate(
    betdate_id: int,
    data: BetDateCreate,
    session: Session = Depends(get_db)
):
    # 1️⃣ Buscar la fecha
    betdate = session.get(BetDate, betdate_id)
    if not betdate:
        raise HTTPException(status_code=404, detail="BetDate no encontrada")

    # 2️⃣ Actualizar campos simples
    betdate.name = data.name
    betdate.start_datetime = data.start_datetime
    betdate.close_datetime = data.close_datetime
    betdate.status = data.status
    betdate.prize_cop = data.prize_cop
    betdate.accumulated_prize = data.accumulated_prize
    betdate.required_credits = data.required_credits

    # 3️⃣ Actualizar partidos (tabla asociativa)
    # borrar relaciones actuales
    session.execute(
        bet_date_matches.delete().where(
            bet_date_matches.c.bet_date_id == betdate_id
        )
    )

    # insertar nuevas relaciones
    for match_id in data.match_ids:
        stmt = insert(bet_date_matches).values(
            bet_date_id=betdate_id,
            match_id=match_id
        )
        session.execute(stmt)

    # 4️⃣ Guardar cambios
    session.commit()
    session.refresh(betdate)

    return BetDateRead.model_validate(betdate)

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
    return betdates
