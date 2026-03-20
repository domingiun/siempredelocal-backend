# backend/app/routes/competitions/stats.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from sqlalchemy import func
from typing import List, Dict, Any, Optional
import logging

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.models.competition.competition import Competition
from app.models.competition.match import Match, MatchStatus
from app.models.competition.round import Round
from app.models.competition.team import Team, CompetitionTeam

router = APIRouter(prefix="/competitions/{competition_id}/stats", tags=["competition-stats"])
logger = logging.getLogger(__name__)

@router.get("/overview")
def get_competition_overview_stats(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener estadísticas generales de la competencia
    """
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
        Match.status == MatchStatus.FINISHED
    ).count()
    
    matches_scheduled = matches_query.filter(
        Match.status == MatchStatus.SCHEDULED
    ).count()
    
    matches_in_progress = matches_query.filter(
        Match.status == MatchStatus.IN_PROGRESS
    ).count()
    
    # Goles totales
    goals_result = db.query(
        func.sum(Match.home_score + Match.away_score)
    ).filter(
        Match.competition_id == competition_id,
        Match.status == MatchStatus.FINISHED
    ).scalar() or 0
    
    # Rondas
    total_rounds = db.query(Round).filter(Round.competition_id == competition_id).count()
    completed_rounds = db.query(Round).filter(
        Round.competition_id == competition_id,
        Round.is_completed == True
    ).count()
    
    # Equipos
    total_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).count()
    
    avg_goals = goals_result / matches_played if matches_played > 0 else 0
    
    return {
        "competition_id": competition_id,
        "competition_name": competition.name,
        "overview": {
            "total_matches": total_matches,
            "matches_played": matches_played,
            "matches_scheduled": matches_scheduled,
            "matches_in_progress": matches_in_progress,
            "goals_scored": goals_result,
            "avg_goals_per_match": round(avg_goals, 2),
            "total_rounds": total_rounds,
            "completed_rounds": completed_rounds,
            "total_teams": total_teams,
            "completion_percentage": round((completed_rounds / total_rounds * 100), 1) if total_rounds > 0 else 0
        }
    }

@router.get("/teams/ranking")
def get_teams_ranking_stats(
    competition_id: int,
    stat_type: str = Query("points", pattern="^(points|goals_for|wins|clean_sheets)$"),
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener ranking de equipos por diferentes estadísticas
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Obtener equipos de la competencia
    competition_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).join(Team).order_by(CompetitionTeam.position).all()
    
    # Seleccionar estadística para ranking
    if stat_type == "points":
        teams_sorted = sorted(
            competition_teams,
            key=lambda x: x.points,
            reverse=True
        )[:limit]
        stat_key = "points"
        stat_name = "Puntos"
    
    elif stat_type == "goals_for":
        teams_sorted = sorted(
            competition_teams,
            key=lambda x: x.goals_for,
            reverse=True
        )[:limit]
        stat_key = "goals_for"
        stat_name = "Goles a favor"
    
    elif stat_type == "wins":
        teams_sorted = sorted(
            competition_teams,
            key=lambda x: x.matches_won,
            reverse=True
        )[:limit]
        stat_key = "matches_won"
        stat_name = "Victorias"
    
    elif stat_type == "clean_sheets":
        # Calcular partidos sin recibir goles
        teams_with_clean_sheets = []
        for ct in competition_teams:
            # Obtener partidos del equipo donde no recibió goles
            clean_matches = db.query(Match).filter(
                Match.competition_id == competition_id,
                Match.status == MatchStatus.FINISHED,
                (
                    (Match.home_team_id == ct.team_id) & (Match.away_score == 0) |
                    (Match.away_team_id == ct.team_id) & (Match.home_score == 0)
                )
            ).count()
            
            teams_with_clean_sheets.append({
                "team": ct.team,
                "clean_sheets": clean_matches,
                "competition_team": ct
            })
        
        teams_sorted = sorted(
            teams_with_clean_sheets,
            key=lambda x: x["clean_sheets"],
            reverse=True
        )[:limit]
        stat_key = "clean_sheets"
        stat_name = "Vallas invictas"
    
    # Formatear respuesta
    ranking = []
    for i, item in enumerate(teams_sorted, 1):
        if stat_type == "clean_sheets":
            team = item["team"]
            competition_team = item["competition_team"]
            stat_value = item["clean_sheets"]
        else:
            team = item.team
            competition_team = item
            stat_value = getattr(competition_team, stat_key)
        
        ranking.append({
            "rank": i,
            "team_id": team.id,
            "team_name": team.name,
            "team_logo": team.logo_url,
            "stat_value": stat_value,
            "position": competition_team.position,
            "matches_played": competition_team.matches_played,
            "points": competition_team.points
        })
    
    return {
        "competition_id": competition_id,
        "stat_type": stat_type,
        "stat_name": stat_name,
        "ranking": ranking
    }

@router.get("/matches")
def get_matches_stats(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener estadísticas detalladas de partidos
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Partidos finalizados
    finished_matches = db.query(Match).filter(
        Match.competition_id == competition_id,
        Match.status == MatchStatus.FINISHED
    ).all()
    
    if not finished_matches:
        return {
            "competition_id": competition_id,
            "total_matches": 0,
            "stats": {}
        }
    
    # Calcular estadísticas
    total_home_wins = 0
    total_away_wins = 0
    total_draws = 0
    total_goals = 0
    total_home_goals = 0
    total_away_goals = 0
    
    match_results = []
    
    for match in finished_matches:
        total_goals += (match.home_score or 0) + (match.away_score or 0)
        total_home_goals += match.home_score or 0
        total_away_goals += match.away_score or 0
        
        if (match.home_score or 0) > (match.away_score or 0):
            total_home_wins += 1
            result = "home_win"
        elif (match.home_score or 0) < (match.away_score or 0):
            total_away_wins += 1
            result = "away_win"
        else:
            total_draws += 1
            result = "draw"
        
        match_results.append({
            "home_score": match.home_score or 0,
            "away_score": match.away_score or 0,
            "result": result
        })
    
    # Calcular promedios
    avg_goals_per_match = total_goals / len(finished_matches)
    avg_home_goals = total_home_goals / len(finished_matches)
    avg_away_goals = total_away_goals / len(finished_matches)
    
    # Distribución de resultados
    home_win_percentage = (total_home_wins / len(finished_matches)) * 100
    away_win_percentage = (total_away_wins / len(finished_matches)) * 100
    draw_percentage = (total_draws / len(finished_matches)) * 100
    
    # Encontrar partido con más goles
    highest_scoring_match = max(
        finished_matches,
        key=lambda m: (m.home_score or 0) + (m.away_score or 0)
    )
    
    return {
        "competition_id": competition_id,
        "total_matches": len(finished_matches),
        "stats": {
            "goals": {
                "total": total_goals,
                "home": total_home_goals,
                "away": total_away_goals,
                "avg_per_match": round(avg_goals_per_match, 2),
                "avg_home": round(avg_home_goals, 2),
                "avg_away": round(avg_away_goals, 2)
            },
            "results": {
                "home_wins": total_home_wins,
                "away_wins": total_away_wins,
                "draws": total_draws,
                "home_win_percentage": round(home_win_percentage, 1),
                "away_win_percentage": round(away_win_percentage, 1),
                "draw_percentage": round(draw_percentage, 1)
            },
            "highest_scoring_match": {
                "match_id": highest_scoring_match.id,
                "home_team": highest_scoring_match.home_team.name if highest_scoring_match.home_team else None,
                "away_team": highest_scoring_match.away_team.name if highest_scoring_match.away_team else None,
                "home_score": highest_scoring_match.home_score or 0,
                "away_score": highest_scoring_match.away_score or 0,
                "total_goals": (highest_scoring_match.home_score or 0) + (highest_scoring_match.away_score or 0)
            }
        }
    }

@router.get("/rounds/progress")
def get_rounds_progress_stats(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener progreso de las rondas/jornadas
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Obtener todas las rondas
    rounds = db.query(Round).filter(
        Round.competition_id == competition_id
    ).order_by(Round.round_number).all()
    
    rounds_progress = []
    
    for round_obj in rounds:
        # Obtener partidos de la ronda
        matches = db.query(Match).filter(
            Match.round_id == round_obj.id
        ).all()
        
        total_matches = len(matches)
        completed_matches = len([m for m in matches if m.status == MatchStatus.FINISHED])
        
        progress_percentage = (completed_matches / total_matches * 100) if total_matches > 0 else 0
        
        rounds_progress.append({
            "round_id": round_obj.id,
            "round_name": round_obj.name,
            "round_number": round_obj.round_number,
            "total_matches": total_matches,
            "completed_matches": completed_matches,
            "progress_percentage": round(progress_percentage, 1),
            "is_completed": round_obj.is_completed,
            "start_date": round_obj.start_date,
            "end_date": round_obj.end_date
        })
    
    return {
        "competition_id": competition_id,
        "total_rounds": len(rounds),
        "completed_rounds": len([r for r in rounds if r.is_completed]),
        "rounds_progress": rounds_progress
    }

@router.get("/goals/timeline")
def get_goals_timeline(
    competition_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener línea temporal de goles por ronda
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    # Obtener rondas ordenadas
    rounds = db.query(Round).filter(
        Round.competition_id == competition_id
    ).order_by(Round.round_number).all()
    
    timeline = []
    
    for round_obj in rounds:
        # Calcular goles en esta ronda
        matches = db.query(Match).filter(
            Match.round_id == round_obj.id,
            Match.status == MatchStatus.FINISHED
        ).all()
        
        round_goals = 0
        for match in matches:
            round_goals += (match.home_score or 0) + (match.away_score or 0)
        
        timeline.append({
            "round_id": round_obj.id,
            "round_name": round_obj.name,
            "round_number": round_obj.round_number,
            "goals": round_goals,
            "total_matches": len(matches),
            "avg_goals_per_match": round(round_goals / len(matches), 2) if len(matches) > 0 else 0
        })
    
    return {
        "competition_id": competition_id,
        "timeline": timeline
    }