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


def build_round_of_32_bracket(
    competition_id: int,
    db: Session,
    allow_incomplete: bool = False
) -> Dict[str, Any]:
    """
    Construye el bracket de dieciseisavos usando posiciones de grupo
    y mejores terceros por subconjuntos de grupos.
    """
    groups = get_group_rankings(competition_id, db)

    # Verificar que todos los grupos A-L existan y esten completos
    required_groups = [chr(65 + i) for i in range(12)]
    missing_groups = [g for g in required_groups if g not in groups]
    if missing_groups:
        return {
            "ready": False,
            "reason": f"Faltan grupos: {', '.join(missing_groups)}"
        }

    incomplete = [g for g, rows in groups.items() if not _group_complete(rows)]
    if incomplete and not allow_incomplete:
        return {
            "ready": False,
            "reason": f"Grupos incompletos: {', '.join(sorted(incomplete))}"
        }

    def pick(group_letter: str, position: int) -> CompetitionTeam:
        rows = groups[group_letter]
        return rows[position - 1]

    # Mapa de terceros por grupo
    third_by_group = {g: rows[2] for g, rows in groups.items()}

    used_thirds = set()

    def best_third_from(groups_subset: List[str]) -> CompetitionTeam | None:
        candidates = [third_by_group[g] for g in groups_subset if g in third_by_group]
        candidates = [c for c in candidates if c.team_id not in used_thirds]
        if not candidates:
            return None
        candidates_sorted = sorted(candidates, key=_sort_key_points, reverse=True)
        chosen = candidates_sorted[0]
        used_thirds.add(chosen.team_id)
        return chosen

    # Definicion de partidos 73-88
    # Construir primero los 8 terceros dinámicos sin asignar a partido aún
    third_74 = best_third_from(list("ABCDF"))
    third_77 = best_third_from(list("CDFGH"))
    third_82 = best_third_from(list("AEHIJ"))
    third_85 = best_third_from(list("EFGIJ"))

    # Intercambiar 74↔77 y 82↔85: el ranking puro no reproduce el bracket FIFA 2026
    third_74, third_77 = third_77, third_74
    third_82, third_85 = third_85, third_82

    matches = [
        {"match_number": 73, "home": pick("A", 2), "away": pick("B", 2),
         "home_label": "2° Grupo A", "away_label": "2° Grupo B"},
        {"match_number": 74, "home": pick("E", 1), "away": third_74,
         "home_label": "1° Grupo E", "away_label": "Mejor 3°"},
        {"match_number": 75, "home": pick("F", 1), "away": pick("C", 2),
         "home_label": "1° Grupo F", "away_label": "2° Grupo C"},
        {"match_number": 76, "home": pick("C", 1), "away": pick("F", 2),
         "home_label": "1° Grupo C", "away_label": "2° Grupo F"},
        {"match_number": 77, "home": pick("I", 1), "away": third_77,
         "home_label": "1° Grupo I", "away_label": "Mejor 3°"},
        {"match_number": 78, "home": pick("E", 2), "away": pick("I", 2),
         "home_label": "2° Grupo E", "away_label": "2° Grupo I"},
        {"match_number": 79, "home": pick("A", 1), "away": best_third_from(list("CEFHI")),
         "home_label": "1° Grupo A", "away_label": "Mejor 3° (C/E/F/H/I)"},
        {"match_number": 80, "home": pick("L", 1), "away": best_third_from(list("EHIJK")),
         "home_label": "1° Grupo L", "away_label": "Mejor 3° (E/H/I/J/K)"},
        {"match_number": 81, "home": pick("D", 1), "away": best_third_from(list("BEFIJ")),
         "home_label": "1° Grupo D", "away_label": "Mejor 3° (B/E/F/I/J)"},
        {"match_number": 82, "home": pick("G", 1), "away": third_82,
         "home_label": "1° Grupo G", "away_label": "Mejor 3°"},
        {"match_number": 83, "home": pick("K", 2), "away": pick("L", 2),
         "home_label": "2° Grupo K", "away_label": "2° Grupo L"},
        {"match_number": 84, "home": pick("H", 1), "away": pick("J", 2),
         "home_label": "1° Grupo H", "away_label": "2° Grupo J"},
        {"match_number": 85, "home": pick("B", 1), "away": third_85,
         "home_label": "1° Grupo B", "away_label": "Mejor 3°"},
        {"match_number": 86, "home": pick("D", 2), "away": pick("G", 2),
         "home_label": "2° Grupo D", "away_label": "2° Grupo G"},
        {"match_number": 87, "home": pick("J", 1), "away": pick("H", 2),
         "home_label": "1° Grupo J", "away_label": "2° Grupo H"},
        {"match_number": 88, "home": pick("K", 1), "away": best_third_from(list("DEIJL")),
         "home_label": "1° Grupo K", "away_label": "Mejor 3° (D/E/I/J/L)"},
    ]

    def to_payload(team_row: CompetitionTeam | None, label: str) -> Dict[str, Any]:
        if not team_row:
            return {"type": "pending", "label": label}
        return {
            "type": "team",
            "team_id": team_row.team_id,
            "name": team_row.team.name if team_row.team else label,
            "group_letter": team_row.group_letter,
            "label": label,
            "points": team_row.points,
            "goal_difference": team_row.goal_difference,
            "goals_for": team_row.goals_for
        }

    def find_winner(team_a: CompetitionTeam | None, team_b: CompetitionTeam | None) -> CompetitionTeam | None:
        if not team_a or not team_b:
            return None
        match = db.query(Match).join(Round, Match.round_id == Round.id).filter(
            Match.competition_id == competition_id,
            Round.round_type.in_([t.value for t in _KNOCKOUT_TYPES]),
            Match.status == MatchStatus.FINISHED,
            or_(
                and_(Match.home_team_id == team_a.team_id, Match.away_team_id == team_b.team_id),
                and_(Match.home_team_id == team_b.team_id, Match.away_team_id == team_a.team_id),
            )
        ).first()
        if not match:
            return None
        hs = match.home_score or 0
        aws = match.away_score or 0
        if hs > aws:
            win_id = match.home_team_id
        elif aws > hs:
            win_id = match.away_team_id
        elif match.penalty_home is not None and match.penalty_away is not None:
            win_id = match.home_team_id if match.penalty_home > match.penalty_away else match.away_team_id
        else:
            return None
        return team_a if team_a.team_id == win_id else team_b

    def pending(label: str) -> Dict[str, Any]:
        return {"type": "pending", "label": label}

    def bracket_entry(num: int, h_team, a_team, h_fallback: str, a_fallback: str) -> Dict[str, Any]:
        return {
            "match_number": num,
            "home": to_payload(h_team, h_fallback) if h_team else pending(h_fallback),
            "away": to_payload(a_team, a_fallback) if a_team else pending(a_fallback),
        }

    round_of_32 = []
    r32_winners: Dict[int, CompetitionTeam | None] = {}
    for m in matches:
        home_p = to_payload(m["home"], m["home_label"])
        away_p = to_payload(m["away"], m["away_label"])
        round_of_32.append({
            "match_number": m["match_number"],
            "home": home_p,
            "away": away_p,
        })
        r32_winners[m["match_number"]] = find_winner(m["home"], m["away"])

    def w32(n): return r32_winners.get(n)

    round_of_16_raw = [
        (89, w32(73), w32(75), "Ganador 73", "Ganador 75"),
        (90, w32(74), w32(77), "Ganador 74", "Ganador 77"),
        (91, w32(76), w32(78), "Ganador 76", "Ganador 78"),
        (92, w32(79), w32(80), "Ganador 79", "Ganador 80"),
        (93, w32(83), w32(84), "Ganador 83", "Ganador 84"),
        (94, w32(81), w32(82), "Ganador 81", "Ganador 82"),
        (95, w32(86), w32(88), "Ganador 86", "Ganador 88"),
        (96, w32(85), w32(87), "Ganador 85", "Ganador 87"),
    ]
    round_of_16 = [bracket_entry(n, h, a, hl, al) for n, h, a, hl, al in round_of_16_raw]
    r16_winners = {n: find_winner(h, a) for n, h, a, *_ in round_of_16_raw}

    def w16(n): return r16_winners.get(n)

    qf_raw = [
        (97, w16(89), w16(90), "Ganador 89", "Ganador 90"),
        (98, w16(93), w16(94), "Ganador 93", "Ganador 94"),
        (99, w16(91), w16(92), "Ganador 91", "Ganador 92"),
        (100, w16(95), w16(96), "Ganador 95", "Ganador 96"),
    ]
    quarterfinals = [bracket_entry(n, h, a, hl, al) for n, h, a, hl, al in qf_raw]
    qf_winners = {n: find_winner(h, a) for n, h, a, *_ in qf_raw}

    def wqf(n): return qf_winners.get(n)

    sf_raw = [
        (101, wqf(97), wqf(98), "Ganador 97", "Ganador 98"),
        (102, wqf(99), wqf(100), "Ganador 99", "Ganador 100"),
    ]
    semifinals = [bracket_entry(n, h, a, hl, al) for n, h, a, hl, al in sf_raw]
    sf_winners = {n: find_winner(h, a) for n, h, a, *_ in sf_raw}
    sf_losers  = {n: (a if find_winner(h, a) is h else h) if find_winner(h, a) else None
                  for n, h, a, *_ in sf_raw}

    third_place = [bracket_entry(103, sf_losers.get(101), sf_losers.get(102), "Perdedor 101", "Perdedor 102")]
    final       = [bracket_entry(104, sf_winners.get(101), sf_winners.get(102), "Ganador 101", "Ganador 102")]

    return {
        "ready": True,
        "provisional": bool(incomplete),
        "reason": f"Grupos incompletos: {', '.join(sorted(incomplete))}" if incomplete else None,
        "round_of_32": round_of_32,
        "round_of_16": round_of_16,
        "quarterfinals": quarterfinals,
        "semifinals": semifinals,
        "third_place": third_place,
        "final": final
    }

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
