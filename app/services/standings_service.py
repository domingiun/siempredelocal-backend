# backend/app/services/standings_service.py
from sqlalchemy.orm import Session
from sqlalchemy import desc, asc, or_, and_
from typing import List, Dict, Any
from datetime import datetime, timedelta
from app.models.competition.match import Match, MatchStatus
from app.models.competition.team import CompetitionTeam, Team
from app.models.competition.round import Round, RoundType

# Tipos de ronda que NO deben afectar la tabla de grupos
_KNOCKOUT_TYPES = {RoundType.ROUND_OF, RoundType.SEMIFINAL, RoundType.FINAL, RoundType.THIRD_PLACE}


def _sort_key_points(team_row):
    return (
        team_row.points,
        team_row.goal_difference,
        team_row.goals_for,
        # Desempate final por nombre del equipo (orden alfabético asc)
        (team_row.team.name if team_row.team else "")
    )


def get_group_rankings(competition_id: int, db: Session) -> Dict[str, List[CompetitionTeam]]:
    """
    Devuelve los equipos ordenados por grupo usando:
    1) puntos, 2) diferencia de gol, 3) goles a favor, 4) nombre
    """
    group_rows = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id,
        CompetitionTeam.group_letter.isnot(None)
    ).join(Team).all()

    groups = {}
    for row in group_rows:
        groups.setdefault(row.group_letter, []).append(row)

    for group_letter, rows in groups.items():
        groups[group_letter] = sorted(rows, key=_sort_key_points, reverse=True)

    return groups


def get_best_thirds(
    competition_id: int,
    db: Session,
    group_letters: List[str] | None = None,
    limit: int = 8
) -> List[CompetitionTeam]:
    """
    Obtiene los mejores terceros de los grupos indicados.
    Orden: puntos, diferencia de gol, goles a favor.
    """
    groups = get_group_rankings(competition_id, db)

    if group_letters:
        group_letters = [g.strip().upper() for g in group_letters if g]
        groups = {k: v for k, v in groups.items() if k in group_letters}

    third_places = []
    for group_letter, rows in groups.items():
        if len(rows) >= 3:
            third_places.append(rows[2])

    third_places_sorted = sorted(third_places, key=_sort_key_points, reverse=True)
    return third_places_sorted[:limit]


def _group_complete(group_rows: List[CompetitionTeam]) -> bool:
    if len(group_rows) < 4:
        return False
    # 4 equipos, todos con 3 partidos jugados
    return all((r.matches_played or 0) >= 3 for r in group_rows[:4])


def get_knockout_bracket(competition_id: int, db: Session) -> Dict[str, Any]:
    """
    Lee el bracket de eliminatoria directamente de la BD.
    No computa posiciones ni ganadores — devuelve los partidos tal como están
    cargados en cada ronda de eliminatoria, con escudo, marcador y estado.
    """
    from sqlalchemy.orm import joinedload as _joinedload

    knockout_rounds = (
        db.query(Round)
        .filter(
            Round.competition_id == competition_id,
            Round.round_type.in_([t.value for t in _KNOCKOUT_TYPES]),
        )
        .order_by(Round.round_number.asc())
        .all()
    )

    if not knockout_rounds:
        return {"ready": False, "reason": "No hay rondas de eliminatoria definidas", "phases": []}

    def team_slot(team) -> Dict[str, Any]:
        if not team:
            return {"type": "pending", "name": "Por definir", "logo_url": None}
        return {
            "type": "team",
            "team_id": team.id,
            "name": team.name,
            "logo_url": team.logo_url,
        }

    phases = []
    for round_ in knockout_rounds:
        round_matches = (
            db.query(Match)
            .filter(Match.round_id == round_.id)
            .options(_joinedload(Match.home_team), _joinedload(Match.away_team))
            .order_by(Match.match_date.asc(), Match.id.asc())
            .all()
        )

        match_data = []
        for m in round_matches:
            match_data.append({
                "match_number": m.id,
                "home": team_slot(m.home_team),
                "away": team_slot(m.away_team),
                "home_score": m.home_score,
                "away_score": m.away_score,
                "penalty_home": m.penalty_home,
                "penalty_away": m.penalty_away,
                "status": m.status,
                "match_date": m.match_date.isoformat() if m.match_date else None,
                "stadium": m.stadium,
                "city": m.city,
            })

        phases.append({
            "round_id": round_.id,
            "round_name": round_.name,
            "round_type": round_.round_type,
            "round_number": round_.round_number,
            "matches": match_data,
        })

    return {"ready": True, "phases": phases}

def recalculate_competition_standings(competition_id: int, db: Session):
    """
    Recalcula la tabla de posiciones de una competencia
    """
    # Obtener todos los equipos de la competencia
    teams = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).all()

    # Reiniciar estadísticas
    for t in teams:
        t.matches_played = 0
        t.matches_won = 0
        t.matches_drawn = 0
        t.matches_lost = 0
        t.goals_for = 0
        t.goals_against = 0
        t.goal_difference = 0
        t.points = 0
        t.position = 0

    db.commit()

    # Solo partidos de fase de grupos (excluir eliminatorias)
    matches = (
        db.query(Match)
        .join(Round, Match.round_id == Round.id)
        .filter(
            Match.competition_id == competition_id,
            Match.status == MatchStatus.FINISHED,
            Round.round_type.notin_([t.value for t in _KNOCKOUT_TYPES]),
        )
        .all()
    )

    # Procesar cada partido
    for match in matches:
        home_team = next((t for t in teams if t.team_id == match.home_team_id), None)
        away_team = next((t for t in teams if t.team_id == match.away_team_id), None)

        if not home_team or not away_team:
            continue

        home_score = match.home_score or 0
        away_score = match.away_score or 0

        # Actualizar estadísticas del equipo local
        home_team.matches_played += 1
        home_team.goals_for += home_score
        home_team.goals_against += away_score

        # Actualizar estadísticas del equipo visitante
        away_team.matches_played += 1
        away_team.goals_for += away_score
        away_team.goals_against += home_score

        # Determinar resultado
        if home_score > away_score:
            home_team.matches_won += 1
            away_team.matches_lost += 1
            home_team.points += 3
        elif home_score < away_score:
            away_team.matches_won += 1
            home_team.matches_lost += 1
            away_team.points += 3
        else:
            home_team.matches_drawn += 1
            away_team.matches_drawn += 1
            home_team.points += 1
            away_team.points += 1

    # Calcular diferencia de goles
    for team in teams:
        team.goal_difference = team.goals_for - team.goals_against

    # Ordenar por: puntos, diferencia de goles, goles a favor
    teams_sorted = sorted(
        teams,
        key=lambda x: (x.points, x.goal_difference, x.goals_for),
        reverse=True
    )

    # Asignar posiciones
    for index, team in enumerate(teams_sorted, start=1):
        team.position = index

    db.commit()

def get_competition_standings(competition_id: int, db: Session) -> List[Dict[str, Any]]:
    """
    Obtiene la tabla de posiciones formateada
    """
    standings = db.query(CompetitionTeam).filter(
        CompetitionTeam.competition_id == competition_id
    ).join(Team).order_by(
        CompetitionTeam.position.asc()
    ).all()

    result = []
    for standing in standings:
        result.append({
            "position": standing.position,
            "team_id": standing.team_id,
            "team_name": standing.team.name,
            "team_short_name": standing.team.short_name,
            "team_logo": standing.team.logo_url,
            "matches_played": standing.matches_played,
            "matches_won": standing.matches_won,
            "matches_drawn": standing.matches_drawn,
            "matches_lost": standing.matches_lost,
            "goals_for": standing.goals_for,
            "goals_against": standing.goals_against,
            "goal_difference": standing.goal_difference,
            "points": standing.points,
            "group_letter": standing.group_letter,
            "group_position": standing.group_position
        })

    return result

def get_team_last_results(team_id: int, db: Session, limit: int = 5) -> List[Dict[str, Any]]:
    """
    Obtiene los últimos resultados de un equipo
    """
    # Obtener partidos del equipo (local o visitante)
    matches = db.query(Match).filter(
        (Match.home_team_id == team_id) | (Match.away_team_id == team_id),
        Match.status == MatchStatus.FINISHED
    ).order_by(
        desc(Match.match_date)
    ).limit(limit).all()

    results = []
    for match in matches:
        is_home = match.home_team_id == team_id
        opponent_id = match.away_team_id if is_home else match.home_team_id
        opponent = db.query(Team).filter(Team.id == opponent_id).first()
        
        result = {
            "match_id": match.id,
            "match_date": match.match_date,
            "competition_id": match.competition_id,
            "round_id": match.round_id,
            "is_home": is_home,
            "opponent_id": opponent_id,
            "opponent_name": opponent.name if opponent else "Desconocido",
            "opponent_logo": opponent.logo_url if opponent else None,
            "team_score": match.home_score if is_home else match.away_score,
            "opponent_score": match.away_score if is_home else match.home_score,
            "stadium": match.stadium,
            "city": match.city
        }
        
        # Determinar resultado (W = Win, D = Draw, L = Loss)
        if result["team_score"] > result["opponent_score"]:
            result["result"] = "W"
        elif result["team_score"] < result["opponent_score"]:
            result["result"] = "L"
        else:
            result["result"] = "D"
        
        results.append(result)

    return results

def get_team_form(team_id: int, db: Session, last_matches: int = 5) -> Dict[str, Any]:
    """
    Obtiene la forma actual del equipo (últimos resultados)
    """
    results = get_team_last_results(team_id, db, last_matches)
    
    wins = sum(1 for r in results if r["result"] == "W")
    draws = sum(1 for r in results if r["result"] == "D")
    losses = sum(1 for r in results if r["result"] == "L")
    
    goals_for = sum(r["team_score"] for r in results)
    goals_against = sum(r["opponent_score"] for r in results)
    
    return {
        "team_id": team_id,
        "last_matches": last_matches,
        "wins": wins,
        "draws": draws,
        "losses": losses,
        "goals_for": goals_for,
        "goals_against": goals_against,
        "goal_difference": goals_for - goals_against,
        "form": "".join([r["result"] for r in results]),  # Ej: "WWDLW"
        "results": results
    }
