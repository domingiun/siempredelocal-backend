# backend/app/routes/admin/rounds.py
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Optional
from datetime import datetime

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.core.dependencies import admin_required

from app.models.competition.round import Round
from app.models.competition.match import Match, MatchStatus
from app.models.competition.competition import Competition
from app.schemas.competition.round import RoundResponse

router = APIRouter(prefix="/admin/rounds", tags=["admin-rounds"])

# -----------------------------
# GET ALL ROUNDS (ADMIN)
# -----------------------------
@router.get("/", response_model=List[RoundResponse])
def get_all_rounds_admin(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    is_completed: Optional[bool] = None,
    competition_id: Optional[int] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)  # SOLO ADMIN
):
    """Obtener todas las jornadas del sistema (solo administradores)"""
    # Construir query base
    query = db.query(Round).options(
        joinedload(Round.competition)  # Cargar competencia
    )
    
    # Aplicar filtros
    if competition_id is not None:
        query = query.filter(Round.competition_id == competition_id)
    
    if is_completed is not None:
        query = query.filter(Round.is_completed == is_completed)
    
    if search:
        query = query.filter(
            (Round.name.ilike(f"%{search}%")) |
            (Competition.name.ilike(f"%{search}%"))
        )
    
    # Ordenar
    query = query.order_by(Round.competition_id, Round.round_number)
    
    # Obtener resultados
    rounds = query.offset(skip).limit(limit).all()
    
    # Para cada jornada, obtener estadísticas
    for round_obj in rounds:
        matches = db.query(Match).filter(
            Match.round_id == round_obj.id
        ).all()
        
        # Agregar propiedades calculadas
        round_obj.total_matches = len(matches)
        round_obj.matches_played = len([m for m in matches if m.status == MatchStatus.FINISHED.value])
        
        # Asegurar que la competencia esté disponible
        if hasattr(round_obj, 'competition') and round_obj.competition:
            round_obj.competition_name = round_obj.competition.name
        else:
            round_obj.competition_name = "Sin competencia"
    
    return rounds

# -----------------------------
# DELETE ROUND (ADMIN)
# -----------------------------
@router.delete("/{round_id}")
def delete_round_admin(
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)  # SOLO ADMIN
):
    """Eliminar jornada (solo administradores)"""
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    # Verificar si la jornada tiene partidos
    matches = db.query(Match).filter(Match.round_id == round_id).all()
    
    if matches:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar: la jornada tiene {len(matches)} partidos asociados"
        )
    
    # Eliminar jornada
    db.delete(round_obj)
    db.commit()
    
    return {"message": "Jornada eliminada correctamente"}