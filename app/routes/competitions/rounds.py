# backend/app/competitions/rounds.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, BackgroundTasks
from sqlalchemy.orm import Session, joinedload
from sqlalchemy import func, case
from typing import List, Optional
from datetime import datetime

from app.db import get_db
from app.models.user.user import User
from app.models.competition.team import Team 
from app.core.security import get_current_user
from app.core.dependencies import admin_required

from app.models.competition.round import Round
from app.models.competition.competition import Competition
from app.models.competition.match import Match, MatchStatus
from app.schemas.competition.round import (
    RoundCreate, RoundUpdate, RoundResponse, RoundWithMatches
)

router = APIRouter(prefix="/competitions/{competition_id}/rounds", tags=["rounds"])

# -----------------------------
# GET ROUNDS
# -----------------------------
@router.get("/", response_model=List[RoundResponse])
def get_rounds(
    competition_id: int,
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    is_completed: Optional[bool] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener jornadas/rondas de una competencia"""
    # Obtener jornadas
    query = db.query(Round).filter(Round.competition_id == competition_id)
    
    if is_completed is not None:
        query = query.filter(Round.is_completed == is_completed)
    
    rounds = query.order_by(Round.round_number)\
                  .offset(skip)\
                  .limit(limit)\
                  .all()
    
    # Para cada jornada, calcular total_matches y matches_played
    from app.models.competition.match import Match, MatchStatus
    
    rounds_response = []
    for round_obj in rounds:
        # Contar partidos
        matches_count = db.query(func.count(Match.id))\
                         .filter(Match.round_id == round_obj.id,
                                 Match.competition_id == competition_id)\
                         .scalar() or 0
        
        # Contar partidos finalizados
        finished_matches = db.query(func.count(Match.id))\
                           .filter(Match.round_id == round_obj.id,
                                   Match.competition_id == competition_id,
                                   Match.status == MatchStatus.FINISHED.value)\
                           .scalar() or 0
        
        round_data = {
            "id": round_obj.id,
            "competition_id": round_obj.competition_id,
            "name": round_obj.name,
            "round_number": round_obj.round_number,
            "round_type": round_obj.round_type.value,
            "phase": round_obj.phase,
            "phase_round": round_obj.phase_round,
            "group_letter": round_obj.group_letter,
            "start_date": round_obj.start_date,
            "end_date": round_obj.end_date,
            "is_completed": round_obj.is_completed,
            "completed_at": round_obj.completed_at,
            "created_at": round_obj.created_at,
            "updated_at": round_obj.updated_at,
            "total_matches": matches_count,
            "matches_played": finished_matches,
            "competition_name": round_obj.competition.name if round_obj.competition else None
        }
        rounds_response.append(round_data)
    
    return rounds_response

# -----------------------------
# GET ROUND BY ID
# -----------------------------
@router.get("/{round_id}", response_model=RoundWithMatches)
def get_round(
    competition_id: int,
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener jornada con sus partidos"""
    # Obtener la jornada con la competencia
    round_obj = db.query(Round).filter(
        Round.id == round_id,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    # Obtener partidos de la jornada CON relaciones de equipos
    matches = db.query(Match)\
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        )\
        .filter(
            Match.round_id == round_id,
            Match.competition_id == competition_id
        )\
        .order_by(Match.match_date, Match.id)\
        .all()
    
    # Verificar duplicados de equipos
    is_valid, message = round_obj.check_team_duplicates(db)
    if not is_valid:
        round_obj.team_duplicate_warning = message
    
    # Actualizar estado de completado
    round_obj.update_completion_status(db, auto_complete=False)
    db.commit()
    db.refresh(round_obj)
    
    # Obtener resumen de partidos
    match_summary = round_obj.get_match_summary(db)
    
    # Obtener equipos involucrados
    teams_involved = round_obj.get_teams_in_round(db)
    
    # CONVERTIR matches a MatchResponse
    matches_response = []
    for match in matches:
        # Asegurarse de que tenemos nombres de equipos
        home_team_name = None
        away_team_name = None
        
        if match.home_team:
            home_team_name = match.home_team.name
        elif match.home_team_id:
            # Intentar obtener el nombre desde la base de datos si no está cargado
            home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
            home_team_name = home_team.name if home_team else f"Equipo {match.home_team_id}"
        
        if match.away_team:
            away_team_name = match.away_team.name
        elif match.away_team_id:
            away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
            away_team_name = away_team.name if away_team else f"Equipo {match.away_team_id}"
        
        # Crear diccionario según MatchResponse
        match_dict = {
            "id": match.id,
            "competition_id": match.competition_id,
            "competition_name": match.competition.name if hasattr(match, 'competition') and match.competition else None,
            "round_id": match.round_id,
            "round_number": round_obj.round_number, 
            "round_name": round_obj.name,
            "round_is_completed": round_obj.is_completed,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "home_team_name": home_team_name,
            "away_team_name": away_team_name,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "status": match.status,
            "match_date": match.match_date,
            "stadium": match.stadium,
            "city": match.city,
            "referee": getattr(match, 'referee', None),
            "created_at": match.created_at,
            "updated_at": match.updated_at,
            # Campos calculados para conveniencia
            "is_finished": match.status == MatchStatus.FINISHED.value,
            "is_in_progress": match.status == MatchStatus.IN_PROGRESS.value,
            "is_scheduled": match.status == MatchStatus.SCHEDULED.value,
            "total_goals": (match.home_score or 0) + (match.away_score or 0),
            "has_score": match.home_score is not None and match.away_score is not None
        }
        
        # Determinar resultado si el partido está finalizado
        if match.status == MatchStatus.FINISHED.value:
            if match.home_score is not None and match.away_score is not None:
                if match.home_score > match.away_score:
                    match_dict["result"] = "home_win"
                    match_dict["winner"] = "home"
                elif match.away_score > match.home_score:
                    match_dict["result"] = "away_win"
                    match_dict["winner"] = "away"
                else:
                    match_dict["result"] = "draw"
                    match_dict["winner"] = "draw"
        
        matches_response.append(match_dict)
    
    # Construir respuesta según RoundWithMatches
    response_data = {
        "id": round_obj.id,
        "competition_id": round_obj.competition_id,
        "name": round_obj.name,
        "round_number": round_obj.round_number,
        "round_type": round_obj.round_type.value,  # Convertir Enum a string
        "phase": round_obj.phase,
        "phase_round": round_obj.phase_round,
        "group_letter": round_obj.group_letter,
        "start_date": round_obj.start_date,
        "end_date": round_obj.end_date,
        "is_completed": round_obj.is_completed,
        "completed_at": round_obj.completed_at,
        "created_at": round_obj.created_at,
        "updated_at": round_obj.updated_at,
        "total_matches": match_summary.get("total_matches", 0),
        "matches_played": match_summary.get("finished_matches", 0),
        "competition_name": round_obj.competition.name if round_obj.competition else None,
        "summary": None,  # De acuerdo con RoundResponse
        "teams_involved": teams_involved,
        # Campos específicos de RoundWithMatches
        "matches": matches_response,
        "match_summary": match_summary
    }
    
    return response_data

# -----------------------------
# CREATE ROUND
# -----------------------------
@router.post("/", response_model=RoundResponse, status_code=status.HTTP_201_CREATED)
def create_round(
    competition_id: int,
    round_data: RoundCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Crear nueva jornada/ronda"""
    # Verificar que la competencia existe
    from app.models.competition.competition import Competition
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Verificar que no exista jornada con mismo número
    existing = db.query(Round).filter(
        Round.competition_id == competition_id,
        Round.round_number == round_data.round_number
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail=f"Ya existe una jornada con el número {round_data.round_number}"
        )
    
    # Crear la jornada
    round_dict = round_data.dict(exclude={"generate_matches"})
    
    round_obj = Round(
        **round_dict,
        competition_id=competition_id
    )
    
    db.add(round_obj)
    db.commit()
    db.refresh(round_obj)
    
    # Generar partidos automáticamente si se solicita
    if round_data.generate_matches:
        background_tasks.add_task(
        generate_matches_for_round,
        round_id=round_obj.id,
        competition_id=competition_id,
        db=db
    )
    
    return round_obj

# -----------------------------
# UPDATE ROUND
# -----------------------------
@router.put("/{round_id}", response_model=RoundResponse)
def update_round(
    competition_id: int,
    round_id: int,
    round_data: RoundUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Actualizar jornada"""
    round_obj = db.query(Round).filter(
        Round.id == round_id,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    # Si se marca como completada, verificar validaciones
    if round_data.is_completed:
        if round_obj.is_completed:
            raise HTTPException(status_code=400, detail="La jornada ya está completada")
        
        matches = db.query(Match).filter(
            Match.round_id == round_id,
            Match.competition_id == competition_id
        ).all()
        
        # Validar mínimo 10 partidos
        if len(matches) < 10:
            raise HTTPException(
                status_code=400,
                detail=f"Una jornada debe tener al menos 10 partidos. Actual: {len(matches)}"
            )
        
        # Validar que no haya equipos duplicados
        is_valid, message = round_obj.check_team_duplicates(db)
        if not is_valid:
            raise HTTPException(status_code=400, detail=message)
        
        # Verificar que todos los partidos estén finalizados
        unfinished_matches = [
            m for m in matches 
            if m.status not in [MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value]
        ]
        
        if unfinished_matches:
            raise HTTPException(
                status_code=400,
                detail=f"No se puede marcar como completada: hay {len(unfinished_matches)} partidos pendientes"
            )
        
        round_data.completed_at = datetime.now()
    
    # Actualizar campos
    update_data = round_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(round_obj, field, value)
    
    # Actualizar estado de completado
    round_obj.update_completion_status(db, auto_complete=False)
    
    db.commit()
    db.refresh(round_obj)
    
    return round_obj

# -----------------------------
# COMPLETE ROUND
# -----------------------------
@router.post("/{round_id}/complete")
def complete_round(
    competition_id: int,
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Marcar jornada como completada (con validaciones completas)"""
    round_obj = db.query(Round).filter(
        Round.id == round_id,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    if round_obj.is_completed:
        raise HTTPException(status_code=400, detail="La jornada ya está completada")
    
    # Verificar partidos
    matches = db.query(Match).filter(
        Match.round_id == round_id,
        Match.competition_id == competition_id
    ).all()
    
    # Validar mínimo 10 partidos
    if len(matches) < 10:
        raise HTTPException(
            status_code=400,
            detail=f"Una jornada debe tener al menos 10 partidos. Actual: {len(matches)}"
        )
    
    # Validar que no haya equipos duplicados
    is_valid, message = round_obj.check_team_duplicates(db)
    if not is_valid:
        raise HTTPException(status_code=400, detail=message)
    
    # Verificar que todos los partidos estén finalizados
    unfinished_matches = [
        m for m in matches 
        if m.status not in [MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value]
    ]
    
    if unfinished_matches:
        raise HTTPException(
            status_code=400,
            detail=f"Hay {len(unfinished_matches)} partidos pendientes"
        )
    
    # Marcar como completada
    round_obj.is_completed = True
    round_obj.completed_at = datetime.now()
    
    db.commit()
    
    return {
        "message": "Jornada marcada como completada",
        "round_id": round_id,
        "total_matches": len(matches),
        "teams_involved": round_obj.get_teams_in_round(db)
    }

# -----------------------------
# VALIDATE ROUND
# -----------------------------
@router.get("/{round_id}/validate")
def validate_round(
    competition_id: int,
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Validar jornada para detectar problemas"""
    round_obj = db.query(Round).filter(
        Round.id == round_id,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    matches = db.query(Match).filter(
        Match.round_id == round_id,
        Match.competition_id == competition_id
    ).all()
    
    # Validaciones
    validation_results = {
        "round_id": round_id,
        "round_name": round_obj.name,
        "total_matches": len(matches),
        "validations": [],
        "is_valid": True
    }
    
    # 1. Validar mínimo de partidos
    if len(matches) < 10:
        validation_results["validations"].append({
            "type": "MIN_MATCHES",
            "status": "FAIL",
            "message": f"La jornada debe tener al menos 10 partidos. Actual: {len(matches)}"
        })
        validation_results["is_valid"] = False
    else:
        validation_results["validations"].append({
            "type": "MIN_MATCHES",
            "status": "PASS",
            "message": f"La jornada tiene {len(matches)} partidos (mínimo: 10)"
        })
    
    # 2. Validar duplicados de equipos
    is_valid, duplicate_message = round_obj.check_team_duplicates(db)
    if not is_valid:
        validation_results["validations"].append({
            "type": "TEAM_DUPLICATES",
            "status": "FAIL",
            "message": duplicate_message
        })
        validation_results["is_valid"] = False
    else:
        validation_results["validations"].append({
            "type": "TEAM_DUPLICATES",
            "status": "PASS",
            "message": "No hay equipos duplicados en la jornada"
        })
    
    # 3. Validar estado de partidos
    scheduled = len([m for m in matches if m.status == MatchStatus.SCHEDULED.value])
    in_progress = len([m for m in matches if m.status == MatchStatus.IN_PROGRESS.value])
    finished = len([m for m in matches if m.status == MatchStatus.FINISHED.value])
    
    validation_results["validations"].append({
        "type": "MATCH_STATUS",
        "status": "INFO",
        "message": f"Partidos: {scheduled} programados, {in_progress} en progreso, {finished} finalizados"
    })
    
    # 4. Verificar si puede completarse
    if round_obj.is_completed:
        validation_results["validations"].append({
            "type": "COMPLETION_STATUS",
            "status": "INFO",
            "message": "La jornada ya está marcada como completada"
        })
    else:
        can_complete = all(
            m.status in [MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value] 
            for m in matches
        )
        
        if can_complete:
            validation_results["validations"].append({
                "type": "CAN_COMPLETE",
                "status": "PASS",
                "message": "La jornada puede marcarse como completada"
            })
        else:
            validation_results["validations"].append({
                "type": "CAN_COMPLETE",
                "status": "FAIL",
                "message": "Hay partidos pendientes que impiden completar la jornada"
            })
            validation_results["is_valid"] = False
    
    return validation_results

# -----------------------------
# AUTO UPDATE ROUND STATUS
# -----------------------------
@router.post("/{round_id}/auto-update")
def auto_update_round_status(
    competition_id: int,
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Actualizar automáticamente el estado de la jornada basado en partidos"""
    round_obj = db.query(Round).filter(
        Round.id == round_id,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    # Guardar estado anterior
    previous_status = round_obj.is_completed
    
    # Actualizar estado
    round_obj.update_completion_status(db, auto_complete=True)
    db.commit()
    db.refresh(round_obj)
    
    status_changed = previous_status != round_obj.is_completed
    
    return {
        "message": "Estado actualizado automáticamente",
        "round_id": round_id,
        "previous_completed": previous_status,
        "current_completed": round_obj.is_completed,
        "status_changed": status_changed,
        "completed_at": round_obj.completed_at,
        "summary": round_obj.get_match_summary(db)
    }

# -----------------------------
# GET ROUNDS SUMMARY
# -----------------------------
@router.get("/summary")
def get_rounds_summary(
    competition_id: int,  # Este viene del prefijo del router
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener resumen de todas las jornadas de una competencia"""
    rounds = db.query(Round).filter(
        Round.competition_id == competition_id
    ).order_by(Round.round_number).all()
    
    summary = {
        "competition_id": competition_id,
        "total_rounds": len(rounds),
        "completed_rounds": len([r for r in rounds if r.is_completed]),
        "in_progress_rounds": len([r for r in rounds if not r.is_completed]),
        "rounds": []
    }
    
    for round_obj in rounds:
        round_summary = round_obj.get_match_summary(db)
        round_info = {
            "id": round_obj.id,
            "name": round_obj.name,
            "round_number": round_obj.round_number,
            "is_completed": round_obj.is_completed,
            "completed_at": round_obj.completed_at,
            **round_summary
        }
        summary["rounds"].append(round_info)
    
    return summary

# -----------------------------
# HELPER FUNCTIONS
# -----------------------------
def generate_matches_for_round(round_id: int, competition_id: int, db: Session):
    """Función de fondo para generar partidos automáticamente"""
    from app.models.competition.team import CompetitionTeam
    from app.models.competition.match import Match
    
    # Obtener equipos de la competencia
    competition_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).all()
    
    if len(competition_teams) < 20:
        # No hay suficientes equipos para generar 10 partidos
        return
    
    # Lógica simple: emparejar equipos (esto es solo un ejemplo)
    # En una implementación real, esto sería más complejo
    teams = [ct.team_id for ct in competition_teams]
    
    # Crear 10 partidos (mínimo requerido)
    matches_to_create = min(10, len(teams) // 2)
    
    for i in range(matches_to_create):
        if i * 2 + 1 < len(teams):
            match = Match(
                competition_id=competition_id,
                round_id=round_id,
                home_team_id=teams[i * 2],
                away_team_id=teams[i * 2 + 1],
                status=MatchStatus.SCHEDULED.value,
                scheduled_at=datetime.now()
            )
            db.add(match)
    
    db.commit()
    
    # Actualizar estado de la jornada
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if round_obj:
        round_obj.update_completion_status(db, auto_complete=False)
        db.commit()
# Agrega esto después del endpoint get_round existente

@router.get("/number/{round_number}", response_model=RoundWithMatches)
def get_round_by_number(
    competition_id: int,
    round_number: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener jornada por número de jornada"""
    # Buscar por número dentro de la competencia
    round_obj = db.query(Round).filter(
        Round.round_number == round_number,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(
            status_code=404, 
            detail=f"Jornada {round_number} no encontrada en esta competencia"
        )
    
    # Reutilizar la lógica del endpoint get_round existente
    matches = db.query(Match)\
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        )\
        .filter(
            Match.round_id == round_obj.id,
            Match.competition_id == competition_id
        )\
        .order_by(Match.match_date, Match.id)\
        .all()
    
    # Verificar duplicados de equipos
    is_valid, message = round_obj.check_team_duplicates(db)
    if not is_valid:
        round_obj.team_duplicate_warning = message
    
    # Actualizar estado de completado
    round_obj.update_completion_status(db, auto_complete=False)
    db.commit()
    db.refresh(round_obj)
    
    # Obtener resumen de partidos
    match_summary = {
        "total_matches": len(matches),
        "finished_matches": len([m for m in matches if m.status == MatchStatus.FINISHED.value]),
        "scheduled_matches": len([m for m in matches if m.status == MatchStatus.SCHEDULED.value]),
        "in_progress_matches": len([m for m in matches if m.status == MatchStatus.IN_PROGRESS.value]),
        "cancelled_matches": len([m for m in matches if m.status == MatchStatus.CANCELLED.value])
    }
    
    # Obtener equipos involucrados
    teams_involved = round_obj.get_teams_in_round(db) if hasattr(round_obj, 'get_teams_in_round') else []
    
    # CONVERTIR matches a diccionarios serializables
    matches_response = []
    for match in matches:
        # Asegurarse de que tenemos nombres de equipos
        home_team_name = None
        away_team_name = None
        
        if match.home_team:
            home_team_name = match.home_team.name
        elif match.home_team_id:
            # Intentar obtener el nombre desde la base de datos si no está cargado
            home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
            home_team_name = home_team.name if home_team else f"Equipo {match.home_team_id}"
        
        if match.away_team:
            away_team_name = match.away_team.name
        elif match.away_team_id:
            away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
            away_team_name = away_team.name if away_team else f"Equipo {match.away_team_id}"
        
        # Crear diccionario según MatchResponse
        match_dict = {
            "id": match.id,
            "competition_id": match.competition_id,
            "competition_name": match.competition.name if hasattr(match, 'competition') and match.competition else None,
            "round_id": match.round_id,
            "round_number": round_obj.round_number, 
            "round_name": round_obj.name,
            "round_is_completed": round_obj.is_completed,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "home_team_name": home_team_name,
            "away_team_name": away_team_name,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "status": match.status,
            "match_date": match.match_date,
            "stadium": match.stadium,
            "city": match.city,
            "referee":  getattr(match, 'referee', None),
            "created_at": match.created_at,
            "updated_at": match.updated_at,
            # Campos calculados para conveniencia
            "is_finished": match.status == MatchStatus.FINISHED.value,
            "is_in_progress": match.status == MatchStatus.IN_PROGRESS.value,
            "is_scheduled": match.status == MatchStatus.SCHEDULED.value,
            "total_goals": (match.home_score or 0) + (match.away_score or 0),
            "has_score": match.home_score is not None and match.away_score is not None
        }
        
        # Determinar resultado si el partido está finalizado
        if match.status == MatchStatus.FINISHED.value:
            if match.home_score is not None and match.away_score is not None:
                if match.home_score > match.away_score:
                    match_dict["result"] = "home_win"
                    match_dict["winner"] = "home"
                elif match.away_score > match.home_score:
                    match_dict["result"] = "away_win"
                    match_dict["winner"] = "away"
                else:
                    match_dict["result"] = "draw"
                    match_dict["winner"] = "draw"
        
        matches_response.append(match_dict)
    
    # Construir respuesta según RoundWithMatches
    response_data = {
        "id": round_obj.id,
        "competition_id": round_obj.competition_id,
        "name": round_obj.name,
        "round_number": round_obj.round_number,
        "round_type": round_obj.round_type.value,
        "phase": round_obj.phase,
        "phase_round": round_obj.phase_round,
        "group_letter": round_obj.group_letter,
        "start_date": round_obj.start_date,
        "end_date": round_obj.end_date,
        "is_completed": round_obj.is_completed,
        "completed_at": round_obj.completed_at,
        "created_at": round_obj.created_at,
        "updated_at": round_obj.updated_at,
        "total_matches": match_summary.get("total_matches", 0),
        "matches_played": match_summary.get("finished_matches", 0),
        "competition_name": round_obj.competition.name if round_obj.competition else None,
        "summary": None,
        "teams_involved": teams_involved,
        # Campos específicos de RoundWithMatches
        "matches": matches_response,
        "match_summary": match_summary
    }
    
    return response_data

def _get_round_details(round_obj, competition_id, db):
    """Función auxiliar para obtener detalles de una jornada"""
    # Obtener partidos
    matches = db.query(Match)\
        .options(
            joinedload(Match.home_team),
            joinedload(Match.away_team)
        )\
        .filter(
            Match.round_id == round_obj.id,
            Match.competition_id == competition_id
        )\
        .all()
    
    # Convertir matches
    matches_response = []
    for match in matches:
        match_dict = {
            "id": match.id,
            "competition_id": match.competition_id,
            "round_id": match.round_id,
            "round_number": round_obj.round_number,  # ¡CORREGIDO! Usar round_obj.round_number
            "round_name": round_obj.name,
            "round_is_completed": round_obj.is_completed,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "home_team_name": match.home_team.name if match.home_team else f"Equipo {match.home_team_id}",
            "away_team_name": match.away_team.name if match.away_team else f"Equipo {match.away_team_id}",
            "home_score": match.home_score,
            "away_score": match.away_score,
            "status": match.status,
            "match_date": match.match_date,
            "stadium": match.stadium,
            "city": match.city,
            "referee": match.referee,
            "created_at": match.created_at,
            "updated_at": match.updated_at,
        }
        matches_response.append(match_dict)
    
    # Obtener resumen de partidos
    match_summary = {
        "total_matches": len(matches),
        "finished_matches": len([m for m in matches if m.status == MatchStatus.FINISHED.value]),
        "scheduled_matches": len([m for m in matches if m.status == MatchStatus.SCHEDULED.value]),
        "in_progress_matches": len([m for m in matches if m.status == MatchStatus.IN_PROGRESS.value]),
        "cancelled_matches": len([m for m in matches if m.status == MatchStatus.CANCELLED.value])
    }
    
    # Obtener equipos involucrados
    teams_involved = list(set([m.home_team_id for m in matches if m.home_team_id] + 
                               [m.away_team_id for m in matches if m.away_team_id]))
    
    # Construir respuesta
    return {
        "id": round_obj.id,
        "competition_id": round_obj.competition_id,
        "name": round_obj.name,
        "round_number": round_obj.round_number,
        "round_type": round_obj.round_type.value,
        "phase": round_obj.phase,
        "phase_round": round_obj.phase_round,
        "group_letter": round_obj.group_letter,
        "start_date": round_obj.start_date,
        "end_date": round_obj.end_date,
        "is_completed": round_obj.is_completed,
        "completed_at": round_obj.completed_at,
        "created_at": round_obj.created_at,
        "updated_at": round_obj.updated_at,
        "total_matches": match_summary["total_matches"],
        "matches_played": match_summary["finished_matches"],
        "competition_name": round_obj.competition.name if round_obj.competition else None,
        "summary": None,
        "teams_involved": teams_involved,
        "matches": matches_response,
        "match_summary": match_summary
    }

@router.get(
    "/round/{round_number}",
    response_model=RoundResponse
)
def get_round_by_number(
    competition_id: int,
    round_number: int,
    db: Session = Depends(get_db)
):
    round_ = (
        db.query(Round)
        .filter(
            Round.competition_id == competition_id,
            Round.number == round_number
        )
        .first()
    )

    if not round_:
        raise HTTPException(
            status_code=404,
            detail="Jornada no encontrada para esta competencia"
        )

    return round_

# -----------------------------
# DELETE ROUND
# -----------------------------
@router.delete("/{round_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_round(
    competition_id: int,
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Eliminar jornada y sus partidos"""
    round_obj = db.query(Round).filter(
        Round.id == round_id,
        Round.competition_id == competition_id
    ).first()
    
    if not round_obj:
        raise HTTPException(status_code=404, detail="Jornada no encontrada")
    
    db.delete(round_obj)
    db.commit()
    return None
