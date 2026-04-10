# backend/app/routes/competition/matches.py 
from fastapi import APIRouter, Depends, HTTPException, status, Query
from sqlalchemy.orm import Session, joinedload, aliased
from typing import List, Optional
from datetime import datetime, timedelta
import logging

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.core.dependencies import admin_required

from app.services.standings_service import recalculate_competition_standings
from app.services.competition_sync_service import sync_after_match_update

from app.models.competition.match import Match, MatchStatus
from app.models.bet.BetDate import BetDate, BetDateStatus
from app.schemas.bet.finalize import FinalizeRequest
from app.routes.bet.finalize import finalize_betdate
from app.models.competition.competition import Competition
from app.models.competition.round import Round
from app.models.competition.team import CompetitionTeam, Team
from app.schemas.competition.match import (
    MatchCreate, MatchUpdate, MatchResponse, MatchSimpleResponse
)

router = APIRouter(prefix="/matches", tags=["Maches"])
logger = logging.getLogger(__name__)

def _update_competition_stats(
    db: Session,
    competition_id: int,
    home_team_id: int,
    away_team_id: int,
    home_score: int,
    away_score: int,
    is_update: bool = False,
    old_home_score: Optional[int] = None,
    old_away_score: Optional[int] = None
):
    """
    Actualiza estadísticas en competition_teams
    """
    try:
        # Obtener o crear registros en competition_teams
        home_stats = db.query(CompetitionTeam).filter(
            CompetitionTeam.competition_id == competition_id,
            CompetitionTeam.team_id == home_team_id
        ).first()
        
        away_stats = db.query(CompetitionTeam).filter(
            CompetitionTeam.competition_id == competition_id,
            CompetitionTeam.team_id == away_team_id
        ).first()
        
        # Si no existen, crearlos
        if not home_stats:
            home_stats = CompetitionTeam(
                competition_id=competition_id,
                team_id=home_team_id,
                matches_played=0,
                wins=0,
                draws=0,
                losses=0,
                goals_for=0,
                goals_against=0,
                goal_difference=0,
                points=0
            )
            db.add(home_stats)
        
        if not away_stats:
            away_stats = CompetitionTeam(
                competition_id=competition_id,
                team_id=away_team_id,
                matches_played=0,
                wins=0,
                draws=0,
                losses=0,
                goals_for=0,
                goals_against=0,
                goal_difference=0,
                points=0
            )
            db.add(away_stats)
        
        db.commit()
        db.refresh(home_stats)
        db.refresh(away_stats)
        
        # Si es una actualización, revertir estadísticas anteriores
        if is_update and old_home_score is not None and old_away_score is not None:
            # Revertir estadísticas del partido anterior
            _revert_match_stats(home_stats, away_stats, old_home_score, old_away_score)
        
        # Aplicar nuevas estadísticas
        home_stats.matches_played += 1
        away_stats.matches_played += 1
        
        home_stats.goals_for += home_score
        home_stats.goals_against += away_score
        
        away_stats.goals_for += away_score
        away_stats.goals_against += home_score
        
        # Calcular diferencia de goles
        home_stats.goal_difference = home_stats.goals_for - home_stats.goals_against
        away_stats.goal_difference = away_stats.goals_for - away_stats.goals_against
        
        # Determinar resultado y puntos
        if home_score > away_score:
            home_stats.wins += 1
            home_stats.points += 3
            away_stats.losses += 1
        elif home_score < away_score:
            away_stats.wins += 1
            away_stats.points += 3
            home_stats.losses += 1
        else:  # Empate
            home_stats.draws += 1
            home_stats.points += 1
            away_stats.draws += 1
            away_stats.points += 1
        
        db.commit()
        print(f"✅ Estadísticas actualizadas: {home_stats.team_id} vs {away_stats.team_id}")
        
    except Exception as e:
        print(f"❌ Error actualizando estadísticas: {str(e)}")
        raise

def _revert_match_stats(
    home_stats: CompetitionTeam,
    away_stats: CompetitionTeam,
    old_home_score: int,
    old_away_score: int
):
    """Reverte estadísticas de un partido anterior"""
    home_stats.matches_played -= 1
    away_stats.matches_played -= 1
    
    home_stats.goals_for -= old_home_score
    home_stats.goals_against -= old_away_score
    
    away_stats.goals_for -= old_away_score
    away_stats.goals_against -= old_home_score
    
    # Revertir resultado y puntos
    if old_home_score > old_away_score:
        home_stats.wins -= 1
        home_stats.points -= 3
        away_stats.losses -= 1
    elif old_home_score < old_away_score:
        away_stats.wins -= 1
        away_stats.points -= 3
        home_stats.losses -= 1
    else:  # Empate
        home_stats.draws -= 1
        home_stats.points -= 1
        away_stats.draws -= 1
        away_stats.points -= 1

# -----------------------------
# GET MATCHES - CORREGIDO
# -----------------------------
from datetime import datetime, date
from fastapi import Query

@router.get("/", response_model=List[MatchSimpleResponse])
def get_matches(
    competition_id: Optional[int] = None,
    round_id: Optional[int] = None,
    team_id: Optional[int] = None,
    country: Optional[str] = None,
    status: Optional[str] = None,
    date_from: Optional[str] = Query(None, description="Fecha inicio en formato YYYY-MM-DD"),
    date_to: Optional[str] = Query(None, description="Fecha fin en formato YYYY-MM-DD"),
    order: Optional[str] = Query(None, description="Orden por fecha: asc|desc"),
    skip: int = Query(0, ge=0),
    limit: int = Query(10, ge=1, le=100),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener lista de partidos con filtros"""
    
    query = db.query(Match)
    
    HomeTeam = aliased(Team)
    AwayTeam = aliased(Team)    
    
    # Aplicar filtros
    if competition_id:
        query = query.filter(Match.competition_id == competition_id)
    
    if round_id:
        query = query.filter(Match.round_id == round_id)
    
    if team_id:
        query = query.filter(
            (Match.home_team_id == team_id) | (Match.away_team_id == team_id)
        )

    if country:
        query = query.join(HomeTeam, Match.home_team)\
                    .join(AwayTeam, Match.away_team)\
                    .filter(
                        (HomeTeam.country == country) |
                        (AwayTeam.country == country)
                    )
    
    if status:
        query = query.filter(Match.status == status)
    
    # Convertir date_from de string a date si existe
    if date_from:
        try:
            # Aceptar varios formatos comunes
            formats_to_try = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"]
            from_date = None
            
            for fmt in formats_to_try:
                try:
                    from_date = datetime.strptime(date_from, fmt).date()
                    break
                except ValueError:
                    continue
            
            if not from_date:
                raise ValueError(f"No se pudo parsear la fecha: {date_from}")
                
            query = query.filter(Match.match_date >= from_date)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Formato de date_from inválido: {date_from}. Use YYYY-MM-DD. Error: {str(e)}"
            )
    
    # Convertir date_to de string a date si existe
    if date_to:
        try:
            formats_to_try = ["%Y-%m-%d", "%Y/%m/%d", "%d-%m-%Y", "%d/%m/%Y"]
            to_date = None
            
            for fmt in formats_to_try:
                try:
                    to_date = datetime.strptime(date_to, fmt).date()
                    break
                except ValueError:
                    continue
            
            if not to_date:
                raise ValueError(f"No se pudo parsear la fecha: {date_to}")
                
            query = query.filter(Match.match_date <= to_date)
        except ValueError as e:
            raise HTTPException(
                status_code=422,
                detail=f"Formato de date_to inválido: {date_to}. Use YYYY-MM-DD. Error: {str(e)}"
            )
    
    # Ordenar por fecha
    if order and order.lower() == "desc":
        query = query.order_by(Match.match_date.desc())
    else:
        query = query.order_by(Match.match_date)
    
    # Incluir relaciones de jornada y competencia
    matches = query.options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.round),
        joinedload(Match.competition)
    ).offset(skip).limit(limit).all()
    
    # Formatear respuesta INCLUYENDO INFORMACIÓN DE JORNADA
    result = []
    for match in matches:
        match_data = {
            "id": match.id,
            "competition_id": match.competition_id,
            "round_id": match.round_id,
            "match_date": match.match_date,
            "created_at": match.created_at,
            "updated_at": match.updated_at,
            "stadium": match.stadium,
            "city": match.city,

            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,

            "home_team_name": match.home_team.name if match.home_team else None,
            "away_team_name": match.away_team.name if match.away_team else None,

            "home_team_country": match.home_team.country if match.home_team else None,
            "away_team_country": match.away_team.country if match.away_team else None,

            "home_team_logo": match.home_team.logo_url if match.home_team else None,
            "away_team_logo": match.away_team.logo_url if match.away_team else None,

            "home_score": match.home_score,
            "away_score": match.away_score,
            "status": match.status,

            "round_name": match.round.name if match.round else None,
            "round_number": match.round.round_number if match.round else None,

            "competition_name": match.competition.name if match.competition else None,
        }

        result.append(match_data)
    
    return result

# -----------------------------
# GET MATCH BY ID - SIMPLIFICADO
# -----------------------------
@router.get("/{match_id}", response_model=MatchResponse)
def get_match(
    match_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener partido por ID con toda la información"""
    match_obj = db.query(Match).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.round),
        joinedload(Match.competition)
    ).filter(Match.id == match_id).first()
    
    if not match_obj:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    
    # Construir respuesta manualmente para evitar problemas de serialización
    response_data = {
        "id": match_obj.id,
        "competition_id": match_obj.competition_id,
        "round_id": match_obj.round_id,
        "home_team_id": match_obj.home_team_id,
        "away_team_id": match_obj.away_team_id,
        "match_date": match_obj.match_date,
        "stadium": match_obj.stadium,
        "city": match_obj.city,
        "home_score": match_obj.home_score,
        "away_score": match_obj.away_score,
        "status": match_obj.status,
        "created_at": match_obj.created_at,
        "updated_at": match_obj.updated_at,
        # Información de equipos como diccionarios
        "home_team": {
            "id": match_obj.home_team.id if match_obj.home_team else match_obj.home_team_id,
            "name": match_obj.home_team.name if match_obj.home_team else None,
            "short_name": match_obj.home_team.short_name if match_obj.home_team else None,
            "logo_url": match_obj.home_team.logo_url if match_obj.home_team else None,
        } if match_obj.home_team else None,
        "away_team": {
            "id": match_obj.away_team.id if match_obj.away_team else match_obj.away_team_id,
            "name": match_obj.away_team.name if match_obj.away_team else None,
            "short_name": match_obj.away_team.short_name if match_obj.away_team else None,
            "logo_url": match_obj.away_team.logo_url if match_obj.away_team else None,
        } if match_obj.away_team else None,
        # Información de jornada
        "round": {
            "id": match_obj.round.id if match_obj.round else match_obj.round_id,
            "name": match_obj.round.name if match_obj.round else None,
            "round_number": match_obj.round.round_number if match_obj.round else None,
        } if match_obj.round else None,
        # Información de competencia
        "competition": {
            "id": match_obj.competition.id if match_obj.competition else match_obj.competition_id,
            "name": match_obj.competition.name if match_obj.competition else None,
        } if match_obj.competition else None,
    }
    
    return response_data


# -----------------------------
# GET MATCH BY ID - PUBLICO
# -----------------------------
@router.get("/public/{match_id}", response_model=MatchResponse)
def get_match_public(
    match_id: int,
    db: Session = Depends(get_db)
):
    """Obtener partido por ID con toda la información (público)"""
    match_obj = db.query(Match).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.round),
        joinedload(Match.competition)
    ).filter(Match.id == match_id).first()
    
    if not match_obj:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    
    response_data = {
        "id": match_obj.id,
        "competition_id": match_obj.competition_id,
        "round_id": match_obj.round_id,
        "home_team_id": match_obj.home_team_id,
        "away_team_id": match_obj.away_team_id,
        "match_date": match_obj.match_date,
        "stadium": match_obj.stadium,
        "city": match_obj.city,
        "home_score": match_obj.home_score,
        "away_score": match_obj.away_score,
        "status": match_obj.status,
        "created_at": match_obj.created_at,
        "updated_at": match_obj.updated_at,
        "home_team": {
            "id": match_obj.home_team.id if match_obj.home_team else match_obj.home_team_id,
            "name": match_obj.home_team.name if match_obj.home_team else None,
            "short_name": match_obj.home_team.short_name if match_obj.home_team else None,
            "logo_url": match_obj.home_team.logo_url if match_obj.home_team else None,
        } if match_obj.home_team else None,
        "away_team": {
            "id": match_obj.away_team.id if match_obj.away_team else match_obj.away_team_id,
            "name": match_obj.away_team.name if match_obj.away_team else None,
            "short_name": match_obj.away_team.short_name if match_obj.away_team else None,
            "logo_url": match_obj.away_team.logo_url if match_obj.away_team else None,
        } if match_obj.away_team else None,
        "round": {
            "id": match_obj.round.id if match_obj.round else match_obj.round_id,
            "name": match_obj.round.name if match_obj.round else None,
            "round_number": match_obj.round.round_number if match_obj.round else None,
        } if match_obj.round else None,
        "competition": {
            "id": match_obj.competition.id if match_obj.competition else match_obj.competition_id,
            "name": match_obj.competition.name if match_obj.competition else None,
        } if match_obj.competition else None,
    }
    
    return response_data


# -----------------------------
# CREATE MATCH 
# -----------------------------
@router.post("/", status_code=status.HTTP_201_CREATED) 
def create_match(
    match_data: MatchCreate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """Crear nuevo partido simplificado"""
    try:
        # ✅ DIAGNÓSTICO: Ver qué datos llegan
        print("=" * 50)
        print("📥 DATOS RECIBIDOS EN CREATE_MATCH:")
        print(f"Status: {match_data.status} (tipo: {type(match_data.status)})")
        print(f"Home score: {match_data.home_score} (tipo: {type(match_data.home_score)})")
        print(f"Away score: {match_data.away_score} (tipo: {type(match_data.away_score)})")
        print(f"Todo el dict: {match_data.dict()}")
        print("=" * 50)
        # 1. Validar competencia
        competition = db.query(Competition).filter(
            Competition.id == match_data.competition_id,
            Competition.is_active == True
        ).first()
        
        if not competition:
            raise HTTPException(
                status_code=404, 
                detail=f"Competencia ID {match_data.competition_id} no encontrada"
            )
        
        # 2. Validar ronda
        round_obj = db.query(Round).filter(
            Round.id == match_data.round_id,
            Round.competition_id == match_data.competition_id
        ).first()
        
        if not round_obj:
            raise HTTPException(
                status_code=404, 
                detail=f"Jornada ID {match_data.round_id} no encontrada"
            )
        
        # 3. Validar equipos
        home_team = db.query(Team).filter(
            Team.id == match_data.home_team_id,
            Team.is_active == True
        ).first()
        
        away_team = db.query(Team).filter(
            Team.id == match_data.away_team_id,
            Team.is_active == True
        ).first()
        
        if not home_team:
            raise HTTPException(
                status_code=404, 
                detail=f"Equipo local ID {match_data.home_team_id} no encontrado"
            )
        
        if not away_team:
            raise HTTPException(
                status_code=404, 
                detail=f"Equipo visitante ID {match_data.away_team_id} no encontrado"
            )
        
        # 4. Validar que no sean el mismo equipo
        if match_data.home_team_id == match_data.away_team_id:
            raise HTTPException(
                status_code=400, 
                detail="Un equipo no puede jugar contra sí mismo"
            )
        
        # 5. Validar duplicado
        existing = db.query(Match).filter(
            Match.round_id == match_data.round_id,
            Match.home_team_id == match_data.home_team_id,
            Match.away_team_id == match_data.away_team_id,
            Match.competition_id == match_data.competition_id
        ).first()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=(
                    f"Ya existe un partido programado entre "
                    f"{home_team.name} y {away_team.name} "
                    f"en la jornada {round_obj.name}"
                )
            )
                    
        # 7. Crear partido (SIMPLIFICADO - ya no necesitas lógica compleja)
        match_dict = match_data.dict()
        
        # El validador ya maneja los scores según el status
        # Solo asegurar estadio y ciudad
        match_dict["stadium"] = match_data.stadium or home_team.stadium
        match_dict["city"] = match_data.city or home_team.city

        match_obj = Match(**match_dict)

        db.add(match_obj)
        db.commit()
        db.refresh(match_obj)
        
        # ✅ NUEVO: LLAMAR A LAS FUNCIONES DE SINCRONIZACIÓN
        sync_after_match_update(match_obj, db)
        recalculate_competition_standings(match_obj.competition_id, db)
        
        print(f"✅ Partido creado ID {match_obj.id}: "
              f"{home_team.name} {match_obj.home_score}-{match_obj.away_score} {away_team.name} | "
              f"Status: {match_obj.status}")
            
        # 8. Cargar relaciones para la respuesta
        match_with_relations = db.query(Match).options(
            joinedload(Match.home_team),
            joinedload(Match.away_team),
            joinedload(Match.round),
            joinedload(Match.competition)
        ).filter(Match.id == match_obj.id).first()
        
        # 9. Log
        print(
            f"✅ Partido creado: {home_team.name} vs {away_team.name} | "
            f"Jornada: {round_obj.name} | "
            f"Usuario: {current_user.username}"
        )
        
        # 10. CONSTRUIR RESPUESTA MANUALMENTE
        response_data = {
            "id": match_with_relations.id,
            "competition_id": match_with_relations.competition_id,
            "round_id": match_with_relations.round_id,
            "home_team_id": match_with_relations.home_team_id,
            "away_team_id": match_with_relations.away_team_id,
            "match_date": match_with_relations.match_date,
            "stadium": match_with_relations.stadium,
            "city": match_with_relations.city,
            "home_score": match_with_relations.home_score,
            "away_score": match_with_relations.away_score,
            "status": match_with_relations.status,
            "created_at": match_with_relations.created_at,
            "updated_at": match_with_relations.updated_at,
            "home_team": {
                "id": match_with_relations.home_team.id if match_with_relations.home_team else None,
                "name": match_with_relations.home_team.name if match_with_relations.home_team else None,
                "short_name": match_with_relations.home_team.short_name if match_with_relations.home_team else None,
                "logo_url": match_with_relations.home_team.logo_url if match_with_relations.home_team else None,
            } if match_with_relations.home_team else None,
            "away_team": {
                "id": match_with_relations.away_team.id if match_with_relations.away_team else None,
                "name": match_with_relations.away_team.name if match_with_relations.away_team else None,
                "short_name": match_with_relations.away_team.short_name if match_with_relations.away_team else None,
                "logo_url": match_with_relations.away_team.logo_url if match_with_relations.away_team else None,
            } if match_with_relations.away_team else None,
            "round": {
                "id": match_with_relations.round.id if match_with_relations.round else None,
                "name": match_with_relations.round.name if match_with_relations.round else None,
                "round_number": match_with_relations.round.round_number if match_with_relations.round else None,
            } if match_with_relations.round else None,
            "competition": {
                "id": match_with_relations.competition.id if match_with_relations.competition else None,
                "name": match_with_relations.competition.name if match_with_relations.competition else None,
            } if match_with_relations.competition else None,
        }
        
        return response_data
        
    except HTTPException:
        raise
        
    except Exception as e:
        db.rollback()
        print(f"❌ Error creando partido: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Error interno: {str(e)}"
        )

# -----------------------------
# UPDATE MATCH 
# -----------------------------
@router.put("/{match_id}")
def update_match(
    match_id: int,
    match_data: MatchUpdate,
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    match_obj = db.query(Match).filter(Match.id == match_id).first()
    
    if not match_obj:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    
    # 1. GUARDAR DATOS ORIGINALES PARA LOG
    original_status = match_obj.status
    original_home_score = match_obj.home_score
    original_away_score = match_obj.away_score
    
    # 2. OBTENER DATOS DE ACTUALIZACIÓN
    update_data = match_data.dict(exclude_unset=True, exclude_none=True)
    
    print(f"🔄 Datos recibidos para actualización: {update_data}")
    
    # 3. VALIDACIÓN CRÍTICA: SI SE MARCA COMO FINALIZADO, DEBE TENER MARCADOR
    if update_data.get('status') == MatchStatus.FINISHED.value:
        # Si NO viene marcador en la actualización
        if 'home_score' not in update_data or 'away_score' not in update_data:
            # Y el partido actual NO tiene marcador
            if match_obj.home_score is None or match_obj.away_score is None:
                raise HTTPException(
                    status_code=400,
                    detail="Para marcar como FINALIZADO, debe especificar el marcador (home_score y away_score)"
                )
            # Si el partido actual SÍ tiene marcador, mantenerlo
            else:
                print("⚠️ Marcando como FINALIZADO sin nuevo marcador, manteniendo el existente")
        # Si viene marcador, asegurarse de que sean números válidos
        else:
            if update_data['home_score'] is None or update_data['away_score'] is None:
                raise HTTPException(
                    status_code=400,
                    detail="El marcador no puede ser nulo para partidos FINALIZADOS"
                )
    
    # 4. FORZAR 0-0 SI ESTADO ES PROGRAMADO
    if update_data.get('status') == MatchStatus.SCHEDULED.value:
        update_data['home_score'] = 0
        update_data['away_score'] = 0
        print("📝 Estado PROGRAMADO - Marcador forzado a 0-0")
    
    # 5. SI SE CAMBIA DE FINALIZADO A OTRO ESTADO, MANTENER MARCADOR
    elif original_status == MatchStatus.FINISHED.value and update_data.get('status') != MatchStatus.FINISHED.value:
        if 'home_score' not in update_data:
            update_data['home_score'] = match_obj.home_score
        if 'away_score' not in update_data:
            update_data['away_score'] = match_obj.away_score
        print(f"📝 Cambiando de FINALIZADO a {update_data.get('status')} - Manteniendo marcador {match_obj.home_score}-{match_obj.away_score}")
    
    # 6. VERIFICAR SI ES UNA COMPETENCIA MUNDIAL (estadio fijo)
    competition = db.query(Competition).filter(
        Competition.id == match_obj.competition_id
    ).first()
    
    is_world_cup = competition and any(keyword in competition.name.lower() 
                                       for keyword in ['world cup', 'mundial', 'copa mundial'])
    
    # 7. SI CAMBIAN EQUIPOS, ACTUALIZAR ESTADIO Y CIUDAD SOLO SI NO ES MUNDIAL
    if 'home_team_id' in update_data and not is_world_cup:
        new_home_team = db.query(Team).filter(Team.id == update_data['home_team_id']).first()
        if new_home_team:
            # Actualizar estadio y ciudad del equipo local
            update_data['stadium'] = new_home_team.stadium
            update_data['city'] = new_home_team.city
            print(f"🏟️ Estadio actualizado a {new_home_team.stadium} por cambio de equipo local")
    
    # 8. SI ES MUNDIAL Y NO HAY ESTADIO ESPECIFICADO, MANTENER EL ACTUAL
    elif is_world_cup and 'stadium' not in update_data:
        # Mantener el estadio actual (estadio neutral del mundial)
        update_data['stadium'] = match_obj.stadium
        update_data['city'] = match_obj.city
    
    # 9. APLICAR CAMBIOS
    for field, value in update_data.items():
        setattr(match_obj, field, value)
    
    # 10. GUARDAR Y RECALCULAR
    db.commit()
    
    # LOG DE CAMBIOS
    print(f"📝 Partido {match_id} modificado por {current_user.username} | "
          f"Estado: {original_status} → {match_obj.status} | "
          f"Marcador: {original_home_score}-{original_away_score} → {match_obj.home_score}-{match_obj.away_score}")
    
    # 11. SINCRONIZAR Y RECALCULAR
    sync_after_match_update(match_obj, db)
    recalculate_competition_standings(match_obj.competition_id, db)

    # 11.1 AUTO-FINALIZAR FECHA SI ESTE FUE EL ÚLTIMO PARTIDO EN FINALIZAR
    if original_status != MatchStatus.FINISHED.value and match_obj.status == MatchStatus.FINISHED.value:
        betdates = (
            db.query(BetDate)
            .join(BetDate.matches)
            .filter(Match.id == match_obj.id)
            .all()
        )
        for betdate in betdates:
            if betdate.status in [BetDateStatus.FINISHED.value, "finished"]:
                continue

            all_finished = all(
                m.status == MatchStatus.FINISHED.value for m in betdate.matches
            )

            if all_finished:
                try:
                    finalize_betdate(
                        betdate.id,
                        request=FinalizeRequest(),
                        session=db
                    )
                    logger.info(
                        "Auto-finalización ejecutada para betdate %s tras finalizar match %s",
                        betdate.id,
                        match_obj.id
                    )
                except HTTPException as e:
                    logger.warning(
                        "Auto-finalización fallida para betdate %s: %s",
                        betdate.id,
                        e.detail
                    )
                except Exception as e:
                    logger.exception(
                        "Error inesperado en auto-finalización para betdate %s: %s",
                        betdate.id,
                        str(e)
                    )
    
    # 12. CARGAR RELACIONES PARA RESPUESTA
    match_with_relations = db.query(Match).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.round),
        joinedload(Match.competition)
    ).filter(Match.id == match_id).first()
    
    # 13. CONSTRUIR RESPUESTA
    response_data = {
        "id": match_with_relations.id,
        "competition_id": match_with_relations.competition_id,
        "round_id": match_with_relations.round_id,
        "home_team_id": match_with_relations.home_team_id,
        "away_team_id": match_with_relations.away_team_id,
        "match_date": match_with_relations.match_date,
        "stadium": match_with_relations.stadium,
        "city": match_with_relations.city,
        "home_score": match_with_relations.home_score,
        "away_score": match_with_relations.away_score,
        "status": match_with_relations.status,
        "created_at": match_with_relations.created_at,
        "updated_at": match_with_relations.updated_at,
        "home_team": {
            "id": match_with_relations.home_team.id if match_with_relations.home_team else None,
            "name": match_with_relations.home_team.name if match_with_relations.home_team else None,
            "logo_url": match_with_relations.home_team.logo_url if match_with_relations.home_team else None,
        } if match_with_relations.home_team else None,
        "away_team": {
            "id": match_with_relations.away_team.id if match_with_relations.away_team else None,
            "name": match_with_relations.away_team.name if match_with_relations.away_team else None,
            "logo_url": match_with_relations.away_team.logo_url if match_with_relations.away_team else None,
        } if match_with_relations.away_team else None,
        "round": {
            "id": match_with_relations.round.id if match_with_relations.round else None,
            "name": match_with_relations.round.name if match_with_relations.round else None,
            "round_number": match_with_relations.round.round_number if match_with_relations.round else None,
        } if match_with_relations.round else None,
        "competition": {
            "id": match_with_relations.competition.id if match_with_relations.competition else None,
            "name": match_with_relations.competition.name if match_with_relations.competition else None,
        } if match_with_relations.competition else None,
    }
    
    return response_data

# -----------------------------
# DELETE MATCH - SIMPLIFICADO
# -----------------------------
@router.delete("/{match_id}", dependencies=[Depends(admin_required)])
def delete_match(
    match_id: int,
    db: Session = Depends(get_db),
    
):
    """Eliminar partido"""
    match_obj = db.query(Match).filter(Match.id == match_id).first()
    
    if not match_obj:
        raise HTTPException(status_code=404, detail="Partido no encontrado")
    
    db.delete(match_obj)
    db.commit()
    
    return {"message": "Partido eliminado exitosamente"}

# -----------------------------
# GET TODAY'S MATCHES - CORREGIDO
# -----------------------------
from datetime import datetime, timedelta

@router.get("/today/upcoming")
def get_today_matches(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener partidos de hoy y próximos"""
    # Usar hora local del servidor (match_date guardado como hora local sin tz)
    now_local = datetime.now()
    start_local = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    start_local_naive = start_local.replace(tzinfo=None)
    end_local_naive = end_local.replace(tzinfo=None)
    
    # Partidos de hoy
    matches_today = db.query(Match).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.competition)
    ).filter(
        Match.match_date >= start_local_naive,
        Match.match_date < end_local_naive,
        (Match.status == MatchStatus.SCHEDULED.value) | (Match.status == "Programado")
    ).order_by(Match.match_date).all()
    
    # Partidos próximos (próximos 7 días)
    next_week_end_local = end_local + timedelta(days=7)
    next_week_end_local_naive = next_week_end_local.replace(tzinfo=None)
    matches_upcoming = db.query(Match).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.competition)
    ).filter(
        Match.match_date >= end_local_naive,
        Match.match_date < next_week_end_local_naive,
        (Match.status == MatchStatus.SCHEDULED.value) | (Match.status == "Programado")
    ).order_by(Match.match_date).all()
    
    # Formatear respuesta CON MÁS INFORMACIÓN
    def format_matches(matches_list):
        return [{
            "id": m.id,
            "competition_id": m.competition_id,
            "round_id": m.round_id,
            "match_date": m.match_date,
            "stadium": m.stadium,
            "city": m.city,
            "home_team_id": m.home_team_id,
            "away_team_id": m.away_team_id,
            "home_team_name": m.home_team.name if m.home_team else None,
            "away_team_name": m.away_team.name if m.away_team else None,
            "home_team_logo": m.home_team.logo_url if m.home_team else None,
            "away_team_logo": m.away_team.logo_url if m.away_team else None,
            "competition_name": m.competition.name if m.competition else None,
            "home_score": m.home_score,
            "away_score": m.away_score,
            "status": m.status.value if hasattr(m.status, "value") else m.status,
            "round_name": m.round.name if m.round else None,
            "round_number": m.round.round_number if m.round else None,
        } for m in matches_list]
    
    return {
        "today": format_matches(matches_today),
        "upcoming": format_matches(matches_upcoming),
        "date": start_local.date().isoformat()
    }

# -----------------------------
# GET MATCHES BY COMPETITION
# -----------------------------
@router.get("/competition/{competition_id}")
def get_matches_by_competition(
    competition_id: int,
    status: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener todos los partidos de una competencia"""
    query = db.query(Match).filter(Match.competition_id == competition_id)
    
    if status:
        query = query.filter(Match.status == status)
    
    matches = query.options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.round)
    ).order_by(Match.match_date).all()
    
    # Estadísticas de la competencia
    total_matches = len(matches)
    finished_matches = len([m for m in matches if m.status == MatchStatus.FINISHED.value])
    scheduled_matches = len([m for m in matches if m.status == MatchStatus.SCHEDULED.value])
    total_goals = sum(m.home_score + m.away_score for m in matches if m.status == MatchStatus.FINISHED.value)
    
    return {
        "competition_id": competition_id,
        "matches": matches,
        "stats": {
            "total_matches": total_matches,
            "finished_matches": finished_matches,
            "scheduled_matches": scheduled_matches,
            "total_goals": total_goals,
            "avg_goals_per_match": round(total_goals / finished_matches, 2) if finished_matches > 0 else 0
        }
    }

# -----------------------------
# GET MATCHES BY ROUND
# -----------------------------
@router.get("/round/{round_id}")
def get_matches_by_round(
    round_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener todos los partidos de una jornada"""
    matches = db.query(Match).filter(
        Match.round_id == round_id
    ).options(
        joinedload(Match.home_team),
        joinedload(Match.away_team)
    ).order_by(Match.match_date).all()
    
    # Verificar si la jornada está completada
    round_obj = db.query(Round).filter(Round.id == round_id).first()
    if round_obj:
        all_finished = all(m.status == MatchStatus.FINISHED.value for m in matches)
        if all_finished and not round_obj.is_completed:
            round_obj.is_completed = True
            round_obj.completed_at = datetime.now()
            db.commit()
    
    return {
        "round_id": round_id,
        "round_name": round_obj.name if round_obj else "Desconocida",
        "matches": matches,
        "total_matches": len(matches),
        "finished_matches": len([m for m in matches if m.status == MatchStatus.FINISHED.value]),
        "is_completed": round_obj.is_completed if round_obj else False
    }

@router.get("/competition/{competition_id}/available-teams")
def get_available_teams_for_competition(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Obtener equipos disponibles para una competencia"""
    try:
        print(f"🔍 Buscando equipos para competencia {competition_id}")
        
        # 1. Obtener información de la competencia
        competition = db.query(Competition).filter(
            Competition.id == competition_id,
            Competition.is_active == True
        ).first()
        
        if not competition:
            raise HTTPException(status_code=404, detail="Competencia no encontrada")
        
        print(f"🏆 Competencia: {competition.name}")
        
        # 2. Obtener IDs de equipos que YA están en esta competencia (solo para info)
        existing_team_ids = []
        competition_teams = db.query(CompetitionTeam).filter(
            CompetitionTeam.competition_id == competition_id
        ).all()
        
        if competition_teams:
            existing_team_ids = [ct.team_id for ct in competition_teams]
            print(f"📊 Equipos ya en competencia: {len(existing_team_ids)}")
        
        # 3. Determinar país basado en el nombre de la competencia
        competition_name = competition.name.lower()
        competition_country = None
        
        # Mapeo simple
        if any(keyword in competition_name for keyword in ['colombia', 'colombiano', 'liga betplay', 'dimayor']):
            competition_country = 'colombia'
        elif any(keyword in competition_name for keyword in ['argentina', 'argentino', 'superliga']):
            competition_country = 'argentina'
        elif any(keyword in competition_name for keyword in ['españa', 'español', 'la liga']):
            competition_country = 'españa'
        
        print(f"📍 País detectado: {competition_country}")
        
        # 4. Consultar TODOS los equipos activos
        all_teams = db.query(Team).filter(Team.is_active == True).all()
        print(f"👥 Total equipos activos en BD: {len(all_teams)}")
        
        # 5. Filtrar equipos por país (PERO NO excluir los ya en competencia)
        available_teams = []
        for team in all_teams:
            # IMPORTANTE: NO excluir equipos que ya están en la competencia
            # if team.id in existing_team_ids:
            #     continue  # ← ELIMINAR ESTA LÍNEA
            
            # Si hay país definido, verificar compatibilidad
            if competition_country:
                team_compatible = False
                
                # Verificar en campo country
                if team.country and competition_country in team.country.lower():
                    team_compatible = True
                # Verificar en ciudad
                elif team.city and competition_country in team.city.lower():
                    team_compatible = True
                # Verificar en nombre del equipo
                elif team.name and competition_country in team.name.lower():
                    team_compatible = True
                # Si no tiene país definido, incluir por seguridad
                elif not team.country:
                    team_compatible = True
                
                if not team_compatible:
                    continue
            
            available_teams.append(team)
        
        print(f"✅ Equipos disponibles después de filtros: {len(available_teams)}")
        
        # 6. Ordenar alfabéticamente
        available_teams.sort(key=lambda x: x.name.lower())
        
        # 7. Marcar qué equipos ya están en la competencia
        teams_response = []
        for team in available_teams:
            is_already_in_competition = team.id in existing_team_ids
            
            teams_response.append({
                "id": team.id,
                "name": team.name,
                "short_name": team.short_name,
                "logo_url": team.logo_url,
                "stadium": team.stadium,
                "city": team.city,
                "country": team.country,
                "is_active": team.is_active,
                "is_already_in_competition": is_already_in_competition,  # ← NUEVO
                "can_be_selected": True  # ← Siempre true, no excluir
            })
        
        return {
            "competition_id": competition_id,
            "competition_name": competition.name,
            "detected_country": competition_country,
            "existing_teams_count": len(existing_team_ids),
            "total_available": len(teams_response),
            "teams": teams_response
        }
        
    except Exception as e:
        print(f"❌ Error en get_available_teams_for_competition: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(
            status_code=500,
            detail=f"Error interno: {str(e)}"
        )

@router.get(
    "/competitions/{competition_id}/rounds/{round_number}/matches",
    response_model=list[MatchSimpleResponse]
)
def get_matches_by_competition_and_round(
    competition_id: int,
    round_number: int,
    db: Session = Depends(get_db)
):
    round_ = (
        db.query(Round)
        .filter(
            Round.competition_id == competition_id,
            Round.round_number == round_number
        )
        .first()
    )

    if not round_:
        raise HTTPException(
            status_code=404,
            detail="Jornada no encontrada"
        )

    matches = (
    db.query(Match)
    .options(
        joinedload(Match.home_team),
        joinedload(Match.away_team),
        joinedload(Match.round),
        joinedload(Match.competition)
    )
    .filter(Match.round_id == round_.id)
    .all()
)

    result = []
    for match in matches:
        result.append({
            "id": match.id,
            "match_date": match.match_date,
            "stadium": match.stadium,
            "city": match.city,
            "home_team_id": match.home_team_id,
            "away_team_id": match.away_team_id,
            "home_team_name": match.home_team.name if match.home_team else None,
            "away_team_name": match.away_team.name if match.away_team else None,
            "home_team_logo": match.home_team.logo_url if match.home_team else None,
            "away_team_logo": match.away_team.logo_url if match.away_team else None,
            "home_team_country": match.home_team.country if match.home_team else None,
            "away_team_country": match.away_team.country if match.away_team else None,
            "home_score": match.home_score,
            "away_score": match.away_score,
            "status": match.status,
            "competition_id": match.competition_id,
            "round_id": match.round_id,
            "round_name": match.round.name if match.round else None,
            "round_number": match.round.round_number if match.round else None,
            "competition_name": match.competition.name if match.competition else None,
            "api_fixture_id": match.api_fixture_id,
            "api_synced_at": match.api_synced_at,
        })

    return result


# ─────────────────────────────────────────────
# API-FOOTBALL INTEGRATION — ADMIN ENDPOINTS
# ─────────────────────────────────────────────

@router.get("/admin/name-preview")
def api_name_preview(
    date: str = Query(..., description="Fecha YYYY-MM-DD"),
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """
    Compara los nombres de equipos en nuestra BD con los nombres que usa api-football
    para los partidos de una fecha dada.
    Útil para detectar diferencias y renombrar equipos localmente.
    """
    from app.utils.api_football import search_fixtures_for_admin, is_configured, TRACKED_LEAGUES
    from app.tasks.sync_scores import normalize_name, names_match

    if not is_configured():
        raise HTTPException(
            status_code=503,
            detail="API_FOOTBALL_KEY no configurada en Railway."
        )

    fixtures, diag = search_fixtures_for_admin(date)
    if not fixtures:
        return {
            "date": date,
            "comparisons": [],
            "diagnostico": diag,
            "message": (
                f"Sin fixtures en ligas rastreadas para {date}. "
                f"API devolvió {diag.get('total_raw', '?')} fixtures en total. "
                f"Ligas vistas: {diag.get('leagues_seen', [])}. "
                f"Ligas rastreadas: {sorted(TRACKED_LEAGUES)}."
            ),
        }

    # Partidos locales del mismo día
    from datetime import datetime, timedelta
    try:
        day = datetime.strptime(date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="Formato de fecha inválido. Usa YYYY-MM-DD")

    # Ventana ampliada ±1 día para absorber desfases de zona horaria
    local_matches = (
        db.query(Match)
        .options(joinedload(Match.home_team), joinedload(Match.away_team))
        .filter(
            Match.match_date >= day - timedelta(days=1),
            Match.match_date < day + timedelta(days=2),
        )
        .all()
    )

    comparisons = []

    for f in fixtures:
        # Buscar partido local que haga match
        matched_local = None
        for m in local_matches:
            h = m.home_team.name if m.home_team else ""
            a = m.away_team.name if m.away_team else ""
            if names_match(h, f["home_team"]) and names_match(a, f["away_team"]):
                matched_local = m
                break

        comparisons.append({
            "fixture_id":         f["fixture_id"],
            "league":             f["league"],
            "api_home_team":      f["home_team"],
            "api_away_team":      f["away_team"],
            "api_home_logo":      f["home_logo"],
            "api_away_logo":      f["away_logo"],
            "api_status":         f["status_short"],
            "api_home_score":     f["home_score"],
            "api_away_score":     f["away_score"],
            "local_match_id":     matched_local.id if matched_local else None,
            "local_home_team":    matched_local.home_team.name if matched_local and matched_local.home_team else None,
            "local_away_team":    matched_local.away_team.name if matched_local and matched_local.away_team else None,
            "local_home_team_id": matched_local.home_team_id if matched_local else None,
            "local_away_team_id": matched_local.away_team_id if matched_local else None,
            "names_match":        matched_local is not None,
        })

    matched   = sum(1 for c in comparisons if c["names_match"])
    unmatched = len(comparisons) - matched

    return {
        "date": date,
        "api_fixtures": len(fixtures),
        "local_matches": len(local_matches),
        "matched": matched,
        "unmatched": unmatched,
        "comparisons": comparisons,
    }


@router.post("/admin/sync-now")
def sync_now(
    current_user: User = Depends(admin_required),
):
    """
    Ejecuta la sincronización de resultados inmediatamente,
    sin esperar el ciclo de 10 minutos del scheduler.
    """
    from app.tasks.scheduler import trigger_sync_now
    from app.db import SessionLocal

    result = trigger_sync_now(session_factory=SessionLocal)
    return {"message": "Sincronización ejecutada", **result}


@router.get("/admin/sync-status")
def sync_status(
    current_user: User = Depends(admin_required),
    db: Session = Depends(get_db),
):
    """Estado general de la sincronización con api-football."""
    from app.utils.api_football import is_configured, TRACKED_LEAGUES

    total  = db.query(Match).count()
    synced = db.query(Match).filter(Match.api_synced_at.isnot(None)).count()

    return {
        "api_configured":  is_configured(),
        "tracked_leagues": sorted(TRACKED_LEAGUES),
        "total_matches":   total,
        "synced_matches":  synced,
        "pending_matches": total - synced,
    }

