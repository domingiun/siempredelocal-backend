from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any
from datetime import datetime, timedelta
import logging

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.models.competition.competition import Competition, CompetitionStatus
from app.models.competition.team import Team, CompetitionTeam
from app.models.competition.match import Match, MatchStatus
from app.models.competition.round import Round

router = APIRouter(prefix="/dashboard", tags=["dashboard"])
logger = logging.getLogger(__name__)

@router.get("/summary")
def get_dashboard_summary(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener resumen general para el dashboard
    """
    try:
        # 1. Total de competencias
        total_competitions = db.query(Competition).filter(
            Competition.is_active == True
        ).count()
        
        # 2. Competencias activas (en curso o programadas)
        active_competitions = db.query(Competition).filter(
            Competition.is_active == True,
            Competition.status.in_([CompetitionStatus.ONGOING, CompetitionStatus.SCHEDULED])
        ).count()
        
        # 3. Competencias por estado
        competitions_by_status = {
            "draft": db.query(Competition).filter(
                Competition.is_active == True,
                Competition.status == CompetitionStatus.DRAFT
            ).count(),
            "scheduled": db.query(Competition).filter(
                Competition.is_active == True,
                Competition.status == CompetitionStatus.SCHEDULED
            ).count(),
            "ongoing": db.query(Competition).filter(
                Competition.is_active == True,
                Competition.status == CompetitionStatus.ONGOING
            ).count(),
            "completed": db.query(Competition).filter(
                Competition.is_active == True,
                Competition.status == CompetitionStatus.COMPLETED
            ).count(),
        }
        
        # 4. Total de equipos en el sistema
        total_teams = db.query(Team).filter(Team.is_active == True).count()
        
        # 5. Total de partidos programados (no jugados)
        scheduled_matches = db.query(Match).filter(
            Match.status == MatchStatus.SCHEDULED
        ).count()
        
        # 6. Partidos en curso
        in_progress_matches = db.query(Match).filter(
            Match.status == MatchStatus.IN_PROGRESS
        ).count()
        
        # 7. Partidos finalizados
        finished_matches = db.query(Match).filter(
            Match.status == MatchStatus.FINISHED
        ).count()
        
        # 8. Próximos 5 partidos (más cercanos en el tiempo)
        now = datetime.now()
        upcoming_matches = db.query(Match).filter(
            Match.match_date >= now,
            Match.status == MatchStatus.SCHEDULED
        ).order_by(Match.match_date.asc()).limit(5).all()
        
        upcoming_matches_formatted = []
        for match in upcoming_matches:
            upcoming_matches_formatted.append({
                "id": match.id,
                "match_date": match.match_date,
                "competition_id": match.competition_id,
                "competition_name": match.competition.name if match.competition else "Desconocida",
                "home_team_id": match.home_team_id,
                "home_team_name": match.home_team.name if match.home_team else "Desconocido",
                "away_team_id": match.away_team_id,
                "away_team_name": match.away_team.name if match.away_team else "Desconocido",
                "stadium": match.stadium,
                "city": match.city
            })
        
        # 9. Competencias activas (últimas 5)
        active_competitions_list = db.query(Competition).filter(
            Competition.is_active == True,
            Competition.status.in_([CompetitionStatus.ONGOING, CompetitionStatus.SCHEDULED])
        ).order_by(Competition.start_date.desc()).limit(5).all()
        
        active_competitions_formatted = []
        for comp in active_competitions_list:
            # Contar equipos en esta competencia
            teams_count = db.query(CompetitionTeam).filter(
                CompetitionTeam.competition_id == comp.id
            ).count()
            
            # Contar partidos en esta competencia
            matches_count = db.query(Match).filter(
                Match.competition_id == comp.id
            ).count()
            
            active_competitions_formatted.append({
                "id": comp.id,
                "name": comp.name,
                "season": comp.season,
                "country": comp.country,
                "status": comp.status,
                "start_date": comp.start_date,
                "teams_count": teams_count,
                "matches_count": matches_count,
                "type": comp.competition_type
            })
        
        # 10. Estadísticas adicionales
        # Total de goles (en partidos finalizados)
        from sqlalchemy import func
        total_goals_result = db.query(
            func.sum(Match.home_score + Match.away_score)
        ).filter(
            Match.status == MatchStatus.FINISHED
        ).scalar() or 0
        
        # Promedio de goles por partido
        avg_goals = total_goals_result / finished_matches if finished_matches > 0 else 0
        
        # Total de rondas creadas
        total_rounds = db.query(Round).count()
        
        return {
            "summary": {
                "total_competitions": total_competitions,
                "active_competitions": active_competitions,
                "competitions_by_status": competitions_by_status,
                "total_teams": total_teams,
                "scheduled_matches": scheduled_matches,
                "in_progress_matches": in_progress_matches,
                "finished_matches": finished_matches,
                "total_matches": scheduled_matches + in_progress_matches + finished_matches,
                "total_goals": total_goals_result,
                "avg_goals_per_match": round(avg_goals, 2),
                "total_rounds": total_rounds
            },
            "upcoming_matches": upcoming_matches_formatted,
            "active_competitions_list": active_competitions_formatted,
            "last_updated": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo resumen del dashboard: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/quick-stats")
def get_quick_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener estadísticas rápidas para widgets pequeños
    """
    try:
        # Estadísticas que se pueden mostrar en widgets pequeños
        stats = {
            "competitions": {
                "total": db.query(Competition).filter(Competition.is_active == True).count(),
                "ongoing": db.query(Competition).filter(
                    Competition.is_active == True,
                    Competition.status == CompetitionStatus.ONGOING
                ).count(),
                "today_matches": db.query(Match).filter(
                    func.date(Match.match_date) == datetime.now().date(),
                    Match.status == MatchStatus.SCHEDULED
                ).count()
            },
            "teams": {
                "total": db.query(Team).filter(Team.is_active == True).count(),
                "with_logo": db.query(Team).filter(
                    Team.is_active == True,
                    Team.logo_url.isnot(None)
                ).count()
            },
            "matches": {
                "today": db.query(Match).filter(
                    func.date(Match.match_date) == datetime.now().date()
                ).count(),
                "this_week": db.query(Match).filter(
                    Match.match_date >= datetime.now(),
                    Match.match_date <= datetime.now() + timedelta(days=7)
                ).count()
            }
        }
        
        return {
            "stats": stats,
            "timestamp": datetime.now().isoformat()
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo quick stats: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/recent-activity")
def get_recent_activity(
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener actividad reciente (partidos recién finalizados, competencias recién creadas)
    """
    try:
        activity_items = []
        
        # 1. Partidos recién finalizados (últimas 24 horas)
        recent_finished_matches = db.query(Match).filter(
            Match.status == MatchStatus.FINISHED,
            Match.updated_at >= datetime.now() - timedelta(hours=24)
        ).order_by(Match.updated_at.desc()).limit(5).all()
        
        for match in recent_finished_matches:
            activity_items.append({
                "type": "match_finished",
                "title": f"Partido finalizado: {match.home_team.name if match.home_team else 'Local'} {match.home_score or 0} - {match.away_score or 0} {match.away_team.name if match.away_team else 'Visitante'}",
                "description": f"{match.competition.name if match.competition else 'Competencia'}",
                "timestamp": match.updated_at.isoformat() if match.updated_at else match.created_at.isoformat(),
                "data": {
                    "match_id": match.id,
                    "competition_id": match.competition_id,
                    "home_score": match.home_score,
                    "away_score": match.away_score
                }
            })
        
        # 2. Competencias recién creadas (últimas 48 horas)
        recent_competitions = db.query(Competition).filter(
            Competition.created_at >= datetime.now() - timedelta(hours=48),
            Competition.is_active == True
        ).order_by(Competition.created_at.desc()).limit(3).all()
        
        for comp in recent_competitions:
            activity_items.append({
                "type": "competition_created",
                "title": f"Nueva competencia: {comp.name}",
                "description": f"Temporada {comp.season} - {comp.country or 'Sin país'}",
                "timestamp": comp.created_at.isoformat(),
                "data": {
                    "competition_id": comp.id,
                    "season": comp.season,
                    "type": comp.competition_type
                }
            })
        
        # 3. Equipos recién creados (últimas 72 horas)
        recent_teams = db.query(Team).filter(
            Team.created_at >= datetime.now() - timedelta(hours=72),
            Team.is_active == True
        ).order_by(Team.created_at.desc()).limit(2).all()
        
        for team in recent_teams:
            activity_items.append({
                "type": "team_created",
                "title": f"Nuevo equipo: {team.name}",
                "description": f"{team.country or 'Sin país'} - {team.city or 'Sin ciudad'}",
                "timestamp": team.created_at.isoformat(),
                "data": {
                    "team_id": team.id,
                    "country": team.country
                }
            })
        
        # Ordenar por timestamp (más reciente primero)
        activity_items.sort(key=lambda x: x["timestamp"], reverse=True)
        
        return {
            "recent_activity": activity_items[:limit],
            "total_activities": len(activity_items)
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo actividad reciente: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")

@router.get("/calendar")
def get_calendar_events(
    start_date: str = None,
    end_date: str = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener eventos para el calendario (partidos programados)
    """
    try:
        # Parsear fechas o usar valores por defecto
        if start_date:
            start = datetime.fromisoformat(start_date.replace('Z', '+00:00'))
        else:
            start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        if end_date:
            end = datetime.fromisoformat(end_date.replace('Z', '+00:00'))
        else:
            end = start + timedelta(days=30)
        
        # Obtener partidos programados en el rango de fechas
        matches = db.query(Match).filter(
            Match.match_date >= start,
            Match.match_date <= end,
            Match.status == MatchStatus.SCHEDULED
        ).order_by(Match.match_date).all()
        
        calendar_events = []
        for match in matches:
            calendar_events.append({
                "id": match.id,
                "title": f"{match.home_team.name if match.home_team else 'Local'} vs {match.away_team.name if match.away_team else 'Visitante'}",
                "start": match.match_date.isoformat(),
                "end": (match.match_date + timedelta(hours=2)).isoformat(),  # Suponer 2 horas de duración
                "allDay": False,
                "color": "#3B82F6",  # Color azul para partidos
                "extendedProps": {
                    "type": "match",
                    "competition_id": match.competition_id,
                    "competition_name": match.competition.name if match.competition else None,
                    "home_team": match.home_team.name if match.home_team else None,
                    "away_team": match.away_team.name if match.away_team else None,
                    "stadium": match.stadium,
                    "city": match.city
                }
            })
        
        # También agregar fechas de inicio de competencias
        competitions = db.query(Competition).filter(
            Competition.start_date.isnot(None),
            Competition.start_date >= start,
            Competition.start_date <= end,
            Competition.is_active == True
        ).all()
        
        for comp in competitions:
            calendar_events.append({
                "id": f"comp_{comp.id}",
                "title": f"Inicio: {comp.name}",
                "start": comp.start_date.isoformat(),
                "end": comp.start_date.isoformat(),
                "allDay": True,
                "color": "#10B981",  # Color verde para competencias
                "extendedProps": {
                    "type": "competition_start",
                    "competition_id": comp.id,
                    "competition_name": comp.name,
                    "season": comp.season
                }
            })
        
        return {
            "events": calendar_events,
            "start_date": start.isoformat(),
            "end_date": end.isoformat(),
            "total_events": len(calendar_events)
        }
        
    except Exception as e:
        logger.error(f"Error obteniendo eventos del calendario: {str(e)}")
        raise HTTPException(status_code=500, detail="Error interno del servidor")