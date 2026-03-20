# backend/app/routes/competitions/standings.py
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session, joinedload
from typing import List, Dict, Any, Optional
import logging

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.services.standings_service import (
    get_competition_standings,
    recalculate_competition_standings,
    get_group_rankings,
    get_best_thirds,
    build_round_of_32_bracket
)
from app.models.competition.competition import Competition
from app.models.competition.team import CompetitionTeam, Team
from app.schemas.competition.standing import StandingSchema
from app.models.competition.match import Match, MatchStatus
from app.models.competition.round import Round

router = APIRouter(prefix="/competitions/{competition_id}/standings", tags=["standings"])
logger = logging.getLogger(__name__)

@router.get("/", response_model=List[StandingSchema])
def get_standings(
    competition_id: int,
    recalculate: bool = Query(False),
    db: Session = Depends(get_db)
):
    print(f"📥 BACKEND → get_standings | competition_id={competition_id}")

    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    if recalculate:
        recalculate_competition_standings(competition_id, db)

    # Obtener CompetitionTeam con Team cargado usando joinedload
    standings_query = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).join(Team, CompetitionTeam.team_id == Team.id).options(
        joinedload(CompetitionTeam.team)
    ).order_by(
        CompetitionTeam.points.desc(),
        CompetitionTeam.goal_difference.desc(),
        CompetitionTeam.goals_for.desc(),
        CompetitionTeam.goals_against.asc(),  # Menos goles en contra es mejor
        Team.name.asc()  # Último desempate alfabético
    ).all()
    print(f"📊 BACKEND → CompetitionTeam encontrados: {len(standings_query)}")

    if standings_query:
        s = standings_query[0]
        print("🔍 PRIMER CompetitionTeam:")
        print("   team_id:", s.team_id)
        print("   team obj:", s.team)
        if s.team:
            print("   team.name:", s.team.name)
            print("   team.logo_url:", s.team.logo_url)

    enriched_standings = []
    for s in standings_query:
        # Construir manualmente los datos para debug
        standing_data = {
            "id": s.team_id,
            "position": s.position,
            "team_id": s.team_id,
            "team_name": s.team.name if s.team else f"Equipo {s.team_id}",
            "team_logo": s.team.logo_url if s.team else None,
            "team_short_name": s.team.short_name if s.team else None,
            "matches_played": s.matches_played,
            "matches_won": s.matches_won,
            "matches_drawn": s.matches_drawn,
            "matches_lost": s.matches_lost,
            "goals_for": s.goals_for,
            "goals_against": s.goals_against,
            "goal_difference": s.goal_difference,
            "points": s.points
        }
        
        
        # Añadir datos del equipo si existe
        if s.team:
            standing_data["team_name"] = s.team.name
            standing_data["team_logo"] = s.team.logo_url
            standing_data["team_short_name"] = s.team.short_name
        else:
            standing_data["team_name"] = f"Equipo {s.team_id}"
            standing_data["team_logo"] = None
        
        enriched_standings.append(standing_data)
       
        print("📤 BACKEND → standing final (primer item):")
    if enriched_standings:
        print(enriched_standings[0])

    return enriched_standings

@router.get("/groups")
def get_group_standings(
    competition_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtener tablas de posiciones por grupos (si la competencia tiene grupos)
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    if competition.groups <= 0:
        raise HTTPException(
            status_code=400, 
            detail="Esta competencia no tiene fase de grupos"
        )
       
    groups_data = {}
    
    # Obtener equipos agrupados por grupo
    for group_letter in [chr(65 + i) for i in range(competition.groups)]:
        teams_in_group = db.query(CompetitionTeam).filter(
            CompetitionTeam.competition_id == competition_id,
            CompetitionTeam.group_letter == group_letter
        ).join(Team).order_by(
            CompetitionTeam.points.desc(),
            CompetitionTeam.goal_difference.desc(),
            CompetitionTeam.goals_for.desc()
        ).all()
        
        standings = []
        for idx, team in enumerate(teams_in_group, 1):
            standings.append({
            "position": idx,
            "group_position": team.group_position,
            "team_id": team.team_id,
            "team_name": team.team.name,
            "team_short_name": team.team.short_name,
            "team_logo": team.team.logo_url,
            "matches_played": team.matches_played,
            "matches_won": team.matches_won,
            "matches_drawn": team.matches_drawn,
            "matches_lost": team.matches_lost,
            "goals_for": team.goals_for,
            "goals_against": team.goals_against,
            "goal_difference": team.goal_difference,
            "points": team.points,
        })
        
        groups_data[f"Grupo {group_letter}"] = {
            "group_letter": group_letter,
            "total_teams": len(teams_in_group),
            "standings": standings
        }
    
    return {
        "competition_id": competition_id,
        "competition_name": competition.name,
        "groups": competition.groups,
        "groups_data": groups_data
    }

@router.get("/qualification")
def get_qualification_status(
    competition_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtener estado de clasificación (qué equipos clasifican)
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")
    
    if competition.teams_to_qualify <= 0:
        raise HTTPException(
            status_code=400, 
            detail="Esta competencia no tiene clasificación"
        )
    
    # Obtener tabla de posiciones
    standings = get_competition_standings(competition_id, db)
    
    # Determinar qué equipos clasifican
    qualifying_teams = standings[:competition.teams_to_qualify]
    non_qualifying_teams = standings[competition.teams_to_qualify:]
    
    # Determinar zonas de descenso si aplica
    relegation_teams = []
    if competition.relegation_spots > 0 and len(standings) >= competition.relegation_spots:
        relegation_teams = standings[-competition.relegation_spots:]
    
    return {
        "competition_id": competition_id,
        "competition_name": competition.name,
        "qualification": {
            "teams_to_qualify": competition.teams_to_qualify,
            "qualifying_teams": [
                {
                    "position": team["position"],
                    "team_id": team["team_id"],
                    "team_name": team["team_name"],
                    "points": team["points"]
                }
                for team in qualifying_teams
            ],
            "non_qualifying_teams": [
                {
                    "position": team["position"],
                    "team_id": team["team_id"],
                    "team_name": team["team_name"],
                    "points": team["points"]
                }
                for team in non_qualifying_teams
            ]
        },
        "relegation": {
            "relegation_spots": competition.relegation_spots,
            "relegation_teams": [
                {
                    "position": team["position"],
                    "team_id": team["team_id"],
                    "team_name": team["team_name"],
                    "points": team["points"]
                }
                for team in relegation_teams
            ] if relegation_teams else []
        }
    }


@router.get("/qualification-groups")
def get_group_qualification(
    competition_id: int,
    groups: Optional[str] = None,
    best_thirds_limit: int = Query(8, ge=1, le=12),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Obtiene clasificados por grupo y mejores terceros (por puntos, DG, GF).
    groups: lista separada por comas (ej: A,B,C)
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()

    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    if competition.groups <= 0:
        raise HTTPException(status_code=400, detail="Esta competencia no tiene fase de grupos")

    group_letters = None
    if groups:
        group_letters = [g.strip().upper() for g in groups.split(",") if g.strip()]

    group_rankings = get_group_rankings(competition_id, db)
    if group_letters:
        group_rankings = {k: v for k, v in group_rankings.items() if k in group_letters}

    groups_payload = {}
    for group_letter, rows in group_rankings.items():
        groups_payload[f"Grupo {group_letter}"] = {
            "group_letter": group_letter,
            "standings": [
                {
                    "position": idx + 1,
                    "team_id": r.team_id,
                    "team_name": r.team.name if r.team else f"Equipo {r.team_id}",
                    "points": r.points,
                    "goal_difference": r.goal_difference,
                    "goals_for": r.goals_for
                }
                for idx, r in enumerate(rows)
            ]
        }

    best_thirds = get_best_thirds(competition_id, db, group_letters, best_thirds_limit)
    best_thirds_payload = [
        {
            "team_id": r.team_id,
            "team_name": r.team.name if r.team else f"Equipo {r.team_id}",
            "group_letter": r.group_letter,
            "points": r.points,
            "goal_difference": r.goal_difference,
            "goals_for": r.goals_for
        }
        for r in best_thirds
    ]

    return {
        "competition_id": competition_id,
        "competition_name": competition.name,
        "groups": groups_payload,
        "best_thirds": best_thirds_payload
    }


@router.get("/playoff-bracket")
def get_playoff_bracket(
    competition_id: int,
    allow_incomplete: bool = Query(True),
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Devuelve el bracket de dieciseisavos (partidos 73-88) usando:
    puntos, diferencia de gol y goles a favor.
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()

    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    if competition.groups <= 0:
        raise HTTPException(status_code=400, detail="Esta competencia no tiene fase de grupos")

    bracket = build_round_of_32_bracket(competition_id, db, allow_incomplete=allow_incomplete)
    return {
        "competition_id": competition_id,
        "competition_name": competition.name,
        **bracket
    }

@router.get("/history")
def get_standings_history(
    competition_id: int,
    db: Session = Depends(get_db)
) -> Dict[str, Any]:
    """
    Historial de posiciones por jornada (para grafica)
    """
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    # Equipos de la competencia
    teams_query = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).join(Team).order_by(Team.name.asc()).all()

    teams = [{
        "team_id": t.team_id,
        "team_name": t.team.name,
        "team_logo": t.team.logo_url
    } for t in teams_query]

    # Jornadas ordenadas
    rounds = db.query(Round).filter(
        Round.competition_id == competition_id,
        Round.round_number > 0
    ).order_by(Round.round_number.asc()).all()

    if not rounds:
        return {
            "competition_id": competition_id,
            "competition_name": competition.name,
            "rounds": [],
            "series": []
        }

    # Partidos finalizados por jornada
    matches = db.query(Match).join(Round).filter(
        Match.competition_id == competition_id,
        Match.status == MatchStatus.FINISHED.value
    ).order_by(Round.round_number.asc(), Match.match_date.asc(), Match.id.asc()).all()

    matches_by_round = {}
    for m in matches:
        rn = m.round.round_number if m.round else None
        if rn is None or rn <= 0:
            continue
        matches_by_round.setdefault(rn, []).append(m)

    # Estadísticas acumuladas
    stats = {}
    for t in teams:
        stats[t["team_id"]] = {
            "matches_played": 0,
            "matches_won": 0,
            "matches_drawn": 0,
            "matches_lost": 0,
            "goals_for": 0,
            "goals_against": 0,
            "goal_difference": 0,
            "points": 0
        }

    series_map = {t["team_id"]: [] for t in teams}

    def sort_key(team_id):
        s = stats[team_id]
        team_name = next((t["team_name"] for t in teams if t["team_id"] == team_id), "")
        return (
            s["points"],
            s["goal_difference"],
            s["goals_for"],
            -s["goals_against"],
            team_name
        )

    for r in rounds:
        round_matches = matches_by_round.get(r.round_number, [])
        
        for match in round_matches:
            home_id = match.home_team_id
            away_id = match.away_team_id
            if home_id not in stats or away_id not in stats:
                continue

            home_score = match.home_score or 0
            away_score = match.away_score or 0

            stats[home_id]["matches_played"] += 1
            stats[away_id]["matches_played"] += 1
            stats[home_id]["goals_for"] += home_score
            stats[home_id]["goals_against"] += away_score
            stats[away_id]["goals_for"] += away_score
            stats[away_id]["goals_against"] += home_score

            if home_score > away_score:
                stats[home_id]["matches_won"] += 1
                stats[away_id]["matches_lost"] += 1
                stats[home_id]["points"] += 3
            elif home_score < away_score:
                stats[away_id]["matches_won"] += 1
                stats[home_id]["matches_lost"] += 1
                stats[away_id]["points"] += 3
            else:
                stats[home_id]["matches_drawn"] += 1
                stats[away_id]["matches_drawn"] += 1
                stats[home_id]["points"] += 1
                stats[away_id]["points"] += 1

        for team_id in stats:
            stats[team_id]["goal_difference"] = (
                stats[team_id]["goals_for"] - stats[team_id]["goals_against"]
            )

        sorted_team_ids = sorted(
            stats.keys(),
            key=sort_key,
            reverse=True
        )

        positions = {team_id: idx + 1 for idx, team_id in enumerate(sorted_team_ids)}

        for team_id in series_map:
            pos = positions.get(team_id, None)
            series_map[team_id].append({
                "round_number": r.round_number,
                "position": pos if pos and pos > 0 else None,
                "matches_played": stats[team_id]["matches_played"],
                "points": stats[team_id]["points"]
            })

    series = []
    for t in teams:
        series.append({
            "team_id": t["team_id"],
            "team_name": t["team_name"],
            "team_logo": t["team_logo"],
            "data": series_map.get(t["team_id"], [])
        })

    return {
        "competition_id": competition_id,
        "competition_name": competition.name,
        "rounds": [{"round_number": r.round_number, "round_name": r.name} for r in rounds if r.round_number and r.round_number > 0],
        "series": series
    }

@router.get("/with-recent-form", response_model=List[Dict[str, Any]])
def get_standings_with_recent_form(
    competition_id: int,
    recalculate: bool = Query(False),
    form_limit: int = Query(5, ge=1, le=10),  
    db: Session = Depends(get_db)
):
    """
    Obtener tabla de posiciones con forma reciente de cada equipo
    """
    # Verificar que la competencia existe
    competition = db.query(Competition).filter(
        Competition.id == competition_id,
        Competition.is_active == True
    ).first()
    
    if not competition:
        raise HTTPException(status_code=404, detail="Competencia no encontrada")

    # Recalcular si se solicita
    if recalculate:
        recalculate_competition_standings(competition_id, db)

    # Obtener tabla de posiciones
    standings_query = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).join(Team, CompetitionTeam.team_id == Team.id).options(
        joinedload(CompetitionTeam.team)
    ).order_by(
        CompetitionTeam.points.desc(),
        CompetitionTeam.goal_difference.desc(),
        CompetitionTeam.goals_for.desc(),
        CompetitionTeam.goals_against.asc(),
        Team.name.asc()
    ).all()

    # Obtener TODOS los partidos finalizados de esta competencia de una vez
    # Match.status es Enum; solo usar valores válidos del enum.
    finished_status = MatchStatus.FINISHED.value
    finished_matches = db.query(Match).filter(
        Match.competition_id == competition_id,
        Match.status == finished_status
    ).order_by(Match.match_date.desc()).all()
    
    # Crear un diccionario de partidos por equipo para acceso rápido
    team_matches = {}
    for match in finished_matches:
        # Para equipo local
        if match.home_team_id not in team_matches:
            team_matches[match.home_team_id] = []
        team_matches[match.home_team_id].append(match)
        
        # Para equipo visitante
        if match.away_team_id not in team_matches:
            team_matches[match.away_team_id] = []
        team_matches[match.away_team_id].append(match)

    # Procesar cada equipo
    enriched_standings = []
    
    
    for standing in standings_query:
    # Obtener partidos FINALIZADOS del equipo
        team_recent_matches = [
            m for m in team_matches.get(standing.team_id, [])
            if (m.status == finished_status)
            and m.home_score is not None
            and m.away_score is not None
        ]

        # Ordenar por fecha (más reciente primero)
        team_recent_matches.sort(
            key=lambda m: m.match_date or 0,
            reverse=True
        )

        # Limitar a los últimos N partidos
        recent_matches = team_recent_matches[:form_limit]

        # Calcular forma (W / D / L)
        recent_form = []
        for match in recent_matches:
            if match.home_team_id == standing.team_id:
                # Equipo local
                if match.home_score > match.away_score:
                    recent_form.append("W")
                elif match.home_score < match.away_score:
                    recent_form.append("L")
                else:
                    recent_form.append("D")
            else:
                # Equipo visitante
                if match.away_score > match.home_score:
                    recent_form.append("W")
                elif match.away_score < match.home_score:
                    recent_form.append("L")
                else:
                    recent_form.append("D")
    
        # Construir respuesta
        standing_data = {
            "id": standing.id,
            "position": standing.position,
            "team_id": standing.team_id,
            "team_name": standing.team.name if standing.team else f"Equipo {standing.team_id}",
            "team_logo": standing.team.logo_url if standing.team else None,
            "team_short_name": standing.team.short_name if standing.team else None,
            "matches_played": standing.matches_played or 0,
            "matches_won": standing.matches_won or 0,
            "matches_drawn": standing.matches_drawn or 0,
            "matches_lost": standing.matches_lost or 0,
            "goals_for": standing.goals_for or 0,
            "goals_against": standing.goals_against or 0,
            "goal_difference": standing.goal_difference or 0,
            "points": standing.points or 0,
            "recent_form": recent_form,
            "recent_matches_count": len(recent_matches)
        }
        
        enriched_standings.append(standing_data)
        

    return enriched_standings
