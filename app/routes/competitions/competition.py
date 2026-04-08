# backend/app/routes/competitions/competitions.py
import traceback
from fastapi import APIRouter, Depends, HTTPException, Request, status, Query, Body, UploadFile, File
from sqlalchemy.orm import Session
from typing import List, Optional
import logging
import os

from app.utils.file_upload import (
    ALLOWED_EXTENSIONS, validate_image_mime,
    read_with_size_limit, generate_safe_filename,
)
from app.utils.storage import upload_file, delete_file, extract_filename_from_url

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.core.dependencies import admin_required
from app.core.competition_generator import CompetitionGenerator

from app.models.competition.competition import Competition, CompetitionStatus
from app.schemas.competition.competition import (
    CompetitionCreate, CompetitionUpdate, CompetitionResponse,
    CompetitionWithTeams, CompetitionTemplate, CompetitionStats
)
from app.models.competition.team import Team, CompetitionTeam
from app.schemas.competition.team import TeamResponse, AddTeamsToCompetitionRequest
from app.services.standings_service import recalculate_competition_standings

router = APIRouter(prefix="/competitions", tags=["competitions"])
logger = logging.getLogger(__name__)

COMPETITION_LOGO_FOLDER = "competition-logos"  # Carpeta dentro del bucket de Supabase

# -----------------------------
# GET COMPETITIONS
# -----------------------------
@router.get("/", response_model=List[CompetitionResponse])
def get_competitions(
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    status: Optional[str] = None,
    country: Optional[str] = None,
    season: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener lista de competencias"""
    query = db.query(Competition).filter(Competition.is_active == True)
    
    if status:
        query = query.filter(Competition.status == status)
    if country:
        query = query.filter(Competition.country.ilike(f"%{country}%"))
    if season:
        query = query.filter(Competition.season == season)
    
    return query.offset(skip).limit(limit).all()

# -----------------------------
# GET COMPETITION BY ID
# -----------------------------
@router.get("/{competition_id}", response_model=CompetitionWithTeams)
def get_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener competencia por ID con equipos"""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Obtener equipos de la competencia
    competition_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).all()
    
    # Convertir objetos Team a diccionarios o usar el schema
    teams = []
    for ct in competition_teams:
        if ct.team:
            teams.append({
                "id": ct.team.id,
                "name": ct.team.name,
                "short_name": ct.team.short_name,
                "country": ct.team.country,
                "city": ct.team.city,
                "stadium": ct.team.stadium,
                "logo_url": ct.team.logo_url,
                "website": ct.team.website,
                "is_active": ct.team.is_active,
                # Agrega otros campos necesarios
            })
    
    # Convertir competition a diccionario
    competition_dict = {
        "id": competition.id,
        "name": competition.name,
        "description": competition.description,
        "country": competition.country,
        "season": competition.season,
        "logo_url": competition.logo_url,
        "competition_type": competition.competition_type,
        "competition_format": competition.competition_format,
        "total_teams": competition.total_teams,
        "groups": competition.groups,
        "teams_per_group": competition.teams_per_group,
        "teams_to_qualify": competition.teams_to_qualify,
        "promotion_spots": competition.promotion_spots,
        "relegation_spots": competition.relegation_spots,
        "international_spots": competition.international_spots,
        "config": competition.config or {},
        "start_date": competition.start_date,
        "end_date": competition.end_date,
        "status": competition.status,
        "is_active": competition.is_active,
        "created_by": competition.created_by,
        "created_at": competition.created_at,
        "updated_at": competition.updated_at,
        "teams": teams,
        "total_teams_registered": len(teams)
    }
    
    return competition_dict

# -----------------------------
# UPLOAD COMPETITION LOGO
# -----------------------------
@router.post("/{competition_id}/upload-logo")
async def upload_competition_logo(
    competition_id: int,
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Subir logo para una competencia"""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()

    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

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
            folder=COMPETITION_LOGO_FOLDER,
            filename=filename,
            file_data=file_data,
            content_type=file.content_type or "image/jpeg",
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error al subir el archivo")

    # Eliminar logo anterior de Supabase si existe
    if competition.logo_url:
        delete_file(COMPETITION_LOGO_FOLDER, extract_filename_from_url(competition.logo_url))

    competition.logo_url = logo_url
    db.commit()

    logger.info(f"Logo subido para competencia {competition.name}: {competition.logo_url}")
    return {"message": "Logo subido exitosamente", "logo_url": competition.logo_url}

# -----------------------------
# CREATE COMPETITION
# -----------------------------
@router.post("/", response_model=CompetitionResponse, status_code=status.HTTP_201_CREATED)
def create_competition(
    competition_data: CompetitionCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Crear nueva competencia"""
    # Verificar que no exista competencia con mismo nombre y temporada
    existing = db.query(Competition).filter(
        Competition.name == competition_data.name,
        Competition.season == competition_data.season,
        Competition.is_active == True
    ).first()
    
    if existing:
        raise HTTPException(
            status_code=400,
            detail="Ya existe una competencia con ese nombre en esta temporada"
        )
    
    # Verificar equipos si se proporcionaron
    if competition_data.team_ids:
        teams = db.query(Team).filter(
            Team.id.in_(competition_data.team_ids),
            Team.is_active == True
        ).all()
        
        if len(teams) != len(competition_data.team_ids):
            raise HTTPException(
                status_code=400,
                detail="Algunos equipos no existen o están inactivos"
            )
        
        if len(teams) != competition_data.total_teams:
            raise HTTPException(
                status_code=400,
                detail=f"Se requieren {competition_data.total_teams} equipos, se proporcionaron {len(teams)}"
            )
    
    # Crear competencia
    competition = Competition(
        **competition_data.dict(exclude={"team_ids"}),
        created_by=current_user.id,
        status=CompetitionStatus.DRAFT.value
    )
    
    db.add(competition)
    db.commit()
    db.refresh(competition)
    
    # Asociar equipos si se proporcionaron
    if competition_data.team_ids and teams:
        for i, team in enumerate(teams):
            competition_team = CompetitionTeam(
                competition_id=competition.id,
                team_id=team.id,
                group_position=i + 1
            )
            db.add(competition_team)
        
        db.commit()
        db.refresh(competition)
    
    logger.info(f"Competencia creada: {competition.name} por usuario {current_user.id}")
    return competition

# -----------------------------
# UPDATE COMPETITION
# -----------------------------
@router.put("/{competition_id}", response_model=CompetitionResponse)
def update_competition(
    competition_id: int,
    competition_data: CompetitionUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Actualizar competencia"""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    if competition_data.total_teams is not None:
        current_teams = db.query(CompetitionTeam).filter(
            CompetitionTeam.competition_id == competition_id
        ).count()
        if competition_data.total_teams < current_teams:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"No puedes reducir el total de equipos por debajo de los ya registrados. "
                    f"Actual: {current_teams}, solicitado: {competition_data.total_teams}"
                )
            )
    
    # Sin restricción de transición de estado — admin puede cambiar libremente
    
    # Actualizar campos
    update_data = competition_data.dict(exclude_unset=True)
    for field, value in update_data.items():
        setattr(competition, field, value)
    
    db.commit()
    db.refresh(competition)

    if competition_data.status == CompetitionStatus.COMPLETED:
        recalculate_competition_standings(competition_id, db)
    
    return competition

# -----------------------------
# DELETE COMPETITION (SOFT)
# -----------------------------
@router.delete("/{competition_id}")
def delete_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Desactivar competencia (soft delete)"""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    competition.is_active = False
    db.commit()
    
    return {"message": "Competencia desactivada exitosamente"}

# -----------------------------
# GENERATE SCHEDULE
# -----------------------------
@router.post("/{competition_id}/generate-schedule")
def generate_schedule(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Generar calendario automáticamente según tipo de competencia"""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Verificar que tiene equipos
    competition_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).all()
    
    if not competition_teams:
        raise HTTPException(status_code=400, detail="La competencia no tiene equipos registrados")
    
    teams = [ct.team for ct in competition_teams]
    
    try:
        # Generar según tipo de competencia
        generator = CompetitionGenerator()
        
        if competition.competition_type == "league":
            rounds = generator.generate_league_schedule(competition, teams, db)
        elif competition.competition_type == "groups_playoff":
            rounds = generator.generate_group_stage(competition, teams, db)
        elif competition.competition_type in ["cup", "league_cup"]:
            # Primero liga, luego playoff si aplica
            if competition.config.get("phases", []) and "league" in competition.config["phases"]:
                rounds = generator.generate_league_schedule(competition, teams, db)
            # Lógica para playoff según equipos que clasifiquen
        else:
            raise HTTPException(status_code=400, detail="Tipo de competencia no soportado")
        
        # Actualizar estado de competencia
        competition.status = CompetitionStatus.SCHEDULED.value
        db.commit()
        
        return {
            "message": "Calendario generado exitosamente",
            "total_rounds": len(rounds),
            "rounds": [{"id": r.id, "name": r.name} for r in rounds]
        }
    
    except Exception as e:
        db.rollback()
        logger.error(f"Error generando calendario: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Error generando calendario: {str(e)}")

# -----------------------------
# GET TEMPLATES
# -----------------------------
@router.get("/templates/{template_name}", response_model=CompetitionTemplate)
def get_competition_template(
    template_name: str,
    total_teams: int = Query(20, ge=2, le=100),
    current_user: User = Depends(get_current_user)
):
    """Obtener plantilla predefinida para competencia"""
    try:
        generator = CompetitionGenerator()
        template_data = generator.create_competition_template(template_name, total_teams, current_user.id)
        return template_data
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

# -----------------------------
# GET COMPETITION STATS
# -----------------------------
@router.get("/{competition_id}/stats", response_model=CompetitionStats)
def get_competition_stats(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener estadísticas de la competencia"""
    from app.models.competition.match import Match, MatchStatus
    from app.models.competition.round import Round
    from sqlalchemy import func
    
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Estadísticas de partidos
    matches_query = db.query(Match).filter(Match.competition_id == competition_id)
    total_matches = matches_query.count()
    
    matches_played = matches_query.filter(
        Match.status == MatchStatus.FINISHED.value
    ).count()
    
    matches_scheduled = matches_query.filter(
        Match.status == MatchStatus.SCHEDULED.value
    ).count()
    
    matches_in_progress = matches_query.filter(
        Match.status == MatchStatus.IN_PROGRESS.value
    ).count()
    
    # Goles totales
    goals_result = db.query(
        func.sum(Match.home_score + Match.away_score)
    ).filter(
        Match.competition_id == competition_id,
        Match.status == MatchStatus.FINISHED.value
    ).scalar() or 0
    
    # Rondas
    total_rounds = db.query(Round).filter(Round.competition_id == competition_id).count()
    completed_rounds = db.query(Round).filter(
        Round.competition_id == competition_id,
        Round.is_completed == True
    ).count()
    
    avg_goals = goals_result / matches_played if matches_played > 0 else 0
    
    return CompetitionStats(
        total_matches=total_matches,
        matches_played=matches_played,
        matches_scheduled=matches_scheduled,
        matches_in_progress=matches_in_progress,
        goals_scored=goals_result,
        avg_goals_per_match=round(avg_goals, 2),
        total_rounds=total_rounds,
        completed_rounds=completed_rounds
    )

@router.get("/{competition_id}/standings")
def get_competition_standings(
    competition_id: int,
    db: Session = Depends(get_db)
):

    standings = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).order_by(CompetitionTeam.position.asc()).all()

    return standings

# -----------------------------
# ADD TEAMS TO COMPETITION
# -----------------------------
@router.post("/{competition_id}/teams")
def add_teams_to_competition(
    competition_id: int,
    payload: AddTeamsToCompetitionRequest = Body(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Agregar equipos a una competencia"""

    team_ids = payload.team_ids

    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()

    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    # Verificar límite de equipos
    current_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).count()

    if current_teams + len(team_ids) > competition.total_teams:
        raise HTTPException(
            status_code=400,
            detail=(
                f"La competencia solo admite {competition.total_teams} equipos. "
                f"Actualmente tiene {current_teams}, intenta agregar {len(team_ids)}"
            )
        )

    # Verificar equipos válidos y activos
    teams = db.query(Team).filter(
        Team.id.in_(team_ids),
        Team.is_active == True
    ).all()

    if len(teams) != len(team_ids):
        raise HTTPException(
            status_code=400,
            detail="Algunos equipos no existen o están inactivos"
        )

    # Verificar que no estén ya en la competencia
    existing_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id,
        CompetitionTeam.team_id.in_(team_ids)
    ).all()

    if existing_teams:
        existing_ids = [et.team_id for et in existing_teams]
        raise HTTPException(
            status_code=400,
            detail=f"Algunos equipos ya están en la competencia: {existing_ids}"
        )

    # Agregar equipos
    added_teams = []
    for index, team in enumerate(teams, start=1):
        competition_team = CompetitionTeam(
            competition_id=competition_id,
            team_id=team.id,
            group_position=current_teams + index
        )
        db.add(competition_team)
        added_teams.append(team)

    db.commit()

    return {
        "message": f"{len(added_teams)} equipos agregados exitosamente",
        "teams_added": [{"id": t.id, "name": t.name} for t in added_teams]
    }


# -----------------------------
# REMOVE TEAM FROM COMPETITION
# -----------------------------
@router.delete("/{competition_id}/teams/{team_id}")
def remove_team_from_competition(
    competition_id: int,
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Remover equipo de una competencia"""
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()

    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    ct = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id,
        CompetitionTeam.team_id == team_id
    ).first()

    if not ct:
        raise HTTPException(status_code=404, detail="El equipo no está en esta competencia")

    db.delete(ct)
    db.commit()

    return {"message": "Equipo removido exitosamente"}


@router.get("/{competition_id}/teams", response_model=List[TeamResponse])
def get_competition_teams(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener todos los equipos de una competencia específica"""
    # Verificar que la competencia exista y esté activa
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Obtener equipos de la competencia
    teams = db.query(Team).join(
        CompetitionTeam, Team.id == CompetitionTeam.team_id
    ).filter(
        CompetitionTeam.competition_id == competition_id,
        Team.is_active == True
    ).order_by(Team.name).all()
    
    return teams

from fastapi import Request

@router.post("/{competition_id}/teams-debug")
async def add_teams_debug(
    competition_id: int,
    request: Request,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Endpoint para diagnosticar problemas"""
    
    print("=" * 60)
    print("🔍 DEBUG ENDPOINT - DETALLADO")
    print(f"🔍 Competition ID: {competition_id}")
    print(f"🔍 Usuario: {current_user.username}")
    print(f"🔍 Método: {request.method}")
    
    # Leer el body crudo
    body_bytes = await request.body()
    body_str = body_bytes.decode('utf-8') if body_bytes else ""
    
    print(f"🔍 Body crudo (longitud: {len(body_str)}): '{body_str}'")
    print(f"🔍 Content-Type header: {request.headers.get('content-type')}")
    
    # Verificar si es preflight OPTIONS
    if request.method == "OPTIONS":
        print("🔍 Esto es una preflight OPTIONS request")
        return {"message": "CORS preflight"}
    
    try:
        if body_str:
            import json
            body_json = json.loads(body_str)
            print(f"🔍 JSON parseado: {body_json}")
            print(f"🔍 Tipo: {type(body_json)}")
            
            if 'team_ids' in body_json:
                team_ids = body_json['team_ids']
                print(f"🔍 team_ids: {team_ids}")
                print(f"🔍 Tipo team_ids: {type(team_ids)}")
                
                # Validar cada elemento
                for i, tid in enumerate(team_ids):
                    print(f"🔍   [{i}] = {tid} (tipo: {type(tid)})")
        else:
            print("🔍 Body vacío o None")
            
    except json.JSONDecodeError as e:
        print(f"🔍 Error parseando JSON: {str(e)}")
        print(f"🔍 Body que causó error: '{body_str}'")
    except Exception as e:
        print(f"🔍 Error general: {str(e)}")
    
    print("=" * 60)
    return {
        "status": "debug",
        "body_received": body_str,
        "body_length": len(body_str),
        "competition_id": competition_id,
        "headers": dict(request.headers)
    }
