# backend/app/routes/bet/BetPlan.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List
from app.db import get_db
from app.models.bet.BetPlan import BetPlan
from app.schemas.bet.BetPlan import BetPlanCreate, BetPlanRead

router = APIRouter(prefix="/betplans", tags=["BetPlans"])

# Crear plan de apuesta
@router.post("/", response_model=BetPlanRead)
def create_betplan(plan: BetPlanCreate, session: Session = Depends(get_db)):
    new_plan = BetPlan(**plan.model_dump())
    session.add(new_plan)
    session.commit()
    session.refresh(new_plan)
    return new_plan

# Listar planes
@router.get("/", response_model=List[BetPlanRead])
def list_betplans(session: Session = Depends(get_db)):
    result = session.execute(select(BetPlan))
    return result.scalars().all()

# Obtener un plan
@router.get("/{plan_id}", response_model=BetPlanRead)
def get_betplan(plan_id: int, session: Session = Depends(get_db)):
    plan = session.get(BetPlan, plan_id)
    if not plan:
        raise HTTPException(status_code=404, detail="Plan no encontrado")
    return plan
