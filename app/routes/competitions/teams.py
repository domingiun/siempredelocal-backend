# backend/app/routes/competitions/teams.py
from fastapi import APIRouter, Depends, HTTPException, status, Query, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import os

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.core.dependencies import admin_required
from app.utils.file_upload import (
    ALLOWED_EXTENSIONS, validate_image_mime,
    read_with_size_limit, generate_safe_filename,
)
from app.utils.storage import upload_file, delete_file, extract_filename_from_url

from app.models.competition.team import Team
from app.schemas.competition.team import (
    TeamCreate, TeamUpdate, TeamResponse
)

router = APIRouter(prefix="/teams", tags=["teams"])
logger = logging.getLogger(__name__)

LOGO_FOLDER = "logos"  # Carpeta dentro del bucket de Supabase

# -----------------------------
# GET TEAMS (independientes)
# -----------------------------
@router.get("/", response_model=List[TeamResponse])
def get_teams(
    skip: int = Query(0, ge=0),
    limit: int = Query(300, ge=1, le=300),
    country: Optional[str] = None,
    is_active: Optional[bool] = None,
    search: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener lista de equipos (independientes de competencias)"""
    query = db.query(Team)
    
    if is_active is not None:
        query = query.filter(Team.is_active == is_active)
    
    if country:
        query = query.filter(Team.country.ilike(f"%{country}%"))
    
    if search:
        query = query.filter(
            (Team.name.ilike(f"%{search}%")) |
            (Team.short_name.ilike(f"%{search}%")) |
            (Team.stadium.ilike(f"%{search}%"))
        )
    
    query = query.order_by(Team.name)
    
    return query.offset(skip).limit(limit).all()

# -----------------------------
# GET TEAM BY ID
# -----------------------------
@router.get("/{team_id}", response_model=TeamResponse)
def get_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener equipo por ID"""
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    return team

# -----------------------------
# CREATE TEAM
# -----------------------------
@router.post("/", response_model=TeamResponse, status_code=status.HTTP_201_CREATED)
def create_team(
    team_data: TeamCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Crear nuevo equipo"""
    # Verificar unicidad de nombre
    existing_name = db.query(Team).filter(
        Team.name == team_data.name,
        Team.is_active == True
    ).first()
    
    if existing_name:
        raise HTTPException(
            status_code=400,
            detail="Ya existe un equipo con ese nombre"
        )
            
    team = Team(**team_data.dict())
    db.add(team)
    db.commit()
    db.refresh(team)
    
    logger.info(f"Equipo creado: {team.name} por usuario {current_user.id}")
    return team

# -----------------------------
# UPDATE TEAM
# -----------------------------
@router.put("/{team_id}", response_model=TeamResponse)
def update_team(
    team_id: int,
    team_data: TeamUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Actualizar equipo"""
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    # Verificar unicidad si se cambia nombre
    if team_data.name and team_data.name != team.name:
        existing = db.query(Team).filter(
            Team.name == team_data.name,
            Team.id != team_id,
            Team.is_active == True
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail="Ya existe otro equipo con ese nombre"
            )
    
    update_data = team_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(team, field, value)
    
    db.commit()
    db.refresh(team)
    
    return team

# -----------------------------
# DELETE TEAM (SOFT)
# -----------------------------
@router.delete("/{team_id}")
def delete_team(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Desactivar equipo (soft delete)"""
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    # Verificar que el equipo no esté en competencias activas
    from app.models.competition import CompetitionTeam
    from app.models.competition import Competition, CompetitionStatus
    
    active_competitions = db.query(CompetitionTeam).join(Competition).filter(
        CompetitionTeam.team_id == team_id,
        Competition.status.in_([CompetitionStatus.ONGOING.value, CompetitionStatus.SCHEDULED.value]),
        Competition.is_active == True
    ).count()
    
    if active_competitions > 0:
        raise HTTPException(
            status_code=400,
            detail=f"No se puede eliminar el equipo: está en {active_competitions} competencia(s) activa(s)"
        )
    
    team.is_active = False
    db.commit()
    
    return {"message": "Equipo desactivado exitosamente"}

# -----------------------------
# UPLOAD TEAM LOGO
# -----------------------------
@router.post("/{team_id}/upload-logo")
async def upload_team_logo(
    team_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Subir logo para un equipo"""
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    # A1+M1: validar extensión
    file_extension = os.path.splitext(file.filename or "")[1].lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato de archivo no permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # A2: leer con límite de tamaño
    file_data = await read_with_size_limit(file)

    # A1: validar magic bytes reales
    validate_image_mime(file_data[:16], file_extension)

    # Nombre no predecible (M1)
    filename = generate_safe_filename(file_extension)

    # C8: Subir a Supabase Storage
    try:
        logo_url = upload_file(
            folder=LOGO_FOLDER,
            filename=filename,
            file_data=file_data,
            content_type=file.content_type or "image/jpeg",
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error al subir el archivo")

    # Eliminar logo anterior si existe
    if team.logo_url:
        delete_file(LOGO_FOLDER, extract_filename_from_url(team.logo_url))

    team.logo_url = logo_url
    db.commit()
    
    logger.info(f"Logo subido para equipo {team.name}: {logo_url} por usuario {current_user.id}")
    
    return {"message": "Logo subido exitosamente", "logo_url": logo_url}

# -----------------------------
# DELETE TEAM LOGO
# -----------------------------
@router.delete("/{team_id}/logo")
def delete_team_logo(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Eliminar logo de un equipo"""
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    if not team.logo_url:
        raise HTTPException(status_code=400, detail="El equipo no tiene logo")
    
    # C8: Eliminar logo de Supabase Storage
    try:
        delete_file(LOGO_FOLDER, extract_filename_from_url(team.logo_url))
    except Exception as e:
        logger.warning(f"No se pudo eliminar el logo de Supabase: {str(e)}")
    
    # Eliminar la URL de la base de datos
    team.logo_url = None
    db.commit()
    
    return {"message": "Logo eliminado exitosamente"}

# -----------------------------
# GET TEAM STATS
# -----------------------------
@router.get("/{team_id}/stats")
def get_team_stats(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener estadísticas generales del equipo"""
    from app.models.competition.match import Match, MatchStatus
    from sqlalchemy import or_, and_
    
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    # Partidos como local
    home_matches = db.query(Match).filter(
        Match.home_team_id == team_id,
        Match.status == MatchStatus.FINISHED.value
    ).all()
    
    # Partidos como visitante
    away_matches = db.query(Match).filter(
        Match.away_team_id == team_id,
        Match.status == MatchStatus.FINISHED.value
    ).all()
    
    all_matches = home_matches + away_matches
    
    # Calcular estadísticas
    stats = {
        "total_matches": len(all_matches),
        "home_matches": len(home_matches),
        "away_matches": len(away_matches),
        "wins": 0,
        "draws": 0,
        "losses": 0,
        "goals_for": 0,
        "goals_against": 0,
    }
    
    for match in all_matches:
        is_home = match.home_team_id == team_id
        goals_for = match.home_score if is_home else match.away_score
        goals_against = match.away_score if is_home else match.home_score
        
        stats["goals_for"] += goals_for
        stats["goals_against"] += goals_against
        
        if goals_for > goals_against:
            stats["wins"] += 1
        elif goals_for == goals_against:
            stats["draws"] += 1
        else:
            stats["losses"] += 1
    
    stats["goal_difference"] = stats["goals_for"] - stats["goals_against"]
    stats["win_percentage"] = (stats["wins"] / stats["total_matches"] * 100) if stats["total_matches"] > 0 else 0
    
    return stats
