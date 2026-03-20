# backend/app/utils/competition_utils.py 
from typing import Optional, Tuple
from app.models.competition.team import Team

def determine_match_venue(
    home_team: Team,
    stadium: Optional[str] = None,
    city: Optional[str] = None
) -> Tuple[str, str]:
    """
    Determina estadio y ciudad del partido
    
    Regla simple: Usar valores proporcionados o los del equipo local
    """
    final_stadium = stadium or home_team.stadium or "Estadio no especificado"
    final_city = city or home_team.city or "Ciudad no especificada"
    
    return final_stadium, final_city

def validate_team_participation_simple(
    home_team: Team,
    away_team: Team
) -> None:
    """
    Validación básica de equipos
    """
    if home_team.id == away_team.id:
        raise ValueError("Un equipo no puede jugar contra sí mismo")
    
    if not home_team.is_active or not away_team.is_active:
        raise ValueError("Uno o ambos equipos están inactivos")