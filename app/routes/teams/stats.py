# backend/app/routes/teams/stats.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session
from typing import List, Dict, Any
import logging

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.models.competition.team import Team
from app.services.standings_service import get_team_last_results, get_team_form

router = APIRouter(prefix="/teams", tags=["team-stats"])
logger = logging.getLogger(__name__)

@router.get("/{team_id}/stats/overall")
def get_team_overall_stats(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener estadísticas generales de un equipo
    """
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    # Calcular porcentajes
    total_matches = team.matches_played
    win_percentage = (team.matches_won / total_matches * 100) if total_matches > 0 else 0
    draw_percentage = (team.matches_drawn / total_matches * 100) if total_matches > 0 else 0
    loss_percentage = (team.matches_lost / total_matches * 100) if total_matches > 0 else 0
    
    # Calcular promedios
    avg_goals_for = (team.goals_for / total_matches) if total_matches > 0 else 0
    avg_goals_against = (team.goals_against / total_matches) if total_matches > 0 else 0
    
    return {
        "team_id": team.id,
        "team_name": team.name,
        "overall_stats": {
            "matches_played": team.matches_played,
            "matches_won": team.matches_won,
            "matches_drawn": team.matches_drawn,
            "matches_lost": team.matches_lost,
            "goals_for": team.goals_for,
            "goals_against": team.goals_against,
            "goal_difference": team.goal_difference,
            "points": team.points,
            "win_percentage": round(win_percentage, 1),
            "draw_percentage": round(draw_percentage, 1),
            "loss_percentage": round(loss_percentage, 1),
            "avg_goals_for": round(avg_goals_for, 2),
            "avg_goals_against": round(avg_goals_against, 2),
            "avg_points_per_match": round(team.points / total_matches, 2) if total_matches > 0 else 0
        }
    }

@router.get("/{team_id}/stats/last-results")
def get_team_last_results_stats(
    team_id: int,
    limit: int = Query(5, ge=1, le=20),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener últimos resultados de un equipo
    """
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    results = get_team_last_results(team_id, db, limit)
    
    # Calcular estadísticas de los últimos resultados
    if results:
        wins = sum(1 for r in results if r["result"] == "W")
        draws = sum(1 for r in results if r["result"] == "D")
        losses = sum(1 for r in results if r["result"] == "L")
        
        goals_for = sum(r["team_score"] for r in results)
        goals_against = sum(r["opponent_score"] for r in results)
        
        form_stats = {
            "wins": wins,
            "draws": draws,
            "losses": losses,
            "goals_for": goals_for,
            "goals_against": goals_against,
            "goal_difference": goals_for - goals_against,
            "points": (wins * 3) + draws,
            "form": "".join([r["result"] for r in results])
        }
    else:
        form_stats = {
            "wins": 0,
            "draws": 0,
            "losses": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0,
            "form": ""
        }
    
    return {
        "team_id": team_id,
        "team_name": team.name,
        "last_results": results,
        "form_stats": form_stats
    }

@router.get("/{team_id}/stats/form")
def get_team_current_form(
    team_id: int,
    last_matches: int = Query(5, ge=1, le=10),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener forma actual del equipo (últimos resultados)
    """
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    form = get_team_form(team_id, db, last_matches)
    
    return {
        "team_id": team_id,
        "team_name": team.name,
        "form": form
    }

@router.get("/{team_id}/stats/competitions")
def get_team_competitions_stats(
    team_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
) -> Dict[str, Any]:
    """
    Obtener estadísticas del equipo en todas las competencias
    """
    team = db.query(Team).filter(
        Team.id == team_id,
        Team.is_active == True
    ).first()
    
    if not team:
        raise HTTPException(status_code=404, detail="Equipo no encontrado")
    
    from app.models.competition.team import CompetitionTeam
    from app.models.competition.competition import Competition
    
    # Obtener todas las competencias del equipo
    competition_teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.team_id == team_id
    ).join(Competition).filter(
        Competition.is_active == True
    ).all()
    
    competitions_stats = []
    
    for ct in competition_teams:
        competitions_stats.append({
            "competition_id": ct.competition_id,
            "competition_name": ct.competition.name,
            "season": ct.competition.season,
            "position": ct.position,
            "stats": {
                "matches_played": ct.matches_played,
                "matches_won": ct.matches_won,
                "matches_drawn": ct.matches_drawn,
                "matches_lost": ct.matches_lost,
                "goals_for": ct.goals_for,
                "goals_against": ct.goals_against,
                "goal_difference": ct.goal_difference,
                "points": ct.points
            }
        })
    
    return {
        "team_id": team_id,
        "team_name": team.name,
        "competitions_stats": competitions_stats
    }