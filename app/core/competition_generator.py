# backend/app/core/competition_generator.py
import logging
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import random
from datetime import datetime, timedelta

from app.models.competition.competition import Competition, CompetitionType, CompetitionFormat
from app.models.competition.team import Team
from app.models.competition.round import Round
from app.models.competition.match import Match, MatchStatus

logger = logging.getLogger(__name__)

class CompetitionGenerator:
    """Generador de calendarios para competencias"""
    
    def __init__(self):
        self.logger = logging.getLogger(__name__)
    
    def generate_league_schedule(
        self,
        competition: Competition,
        teams: List[Team],
        db: Session
    ) -> List[Round]:
        """
        Genera calendario para liga (todos contra todos)
        
        Args:
            competition: Objeto Competition
            teams: Lista de equipos
            db: Sesión de base de datos
            
        Returns:
            Lista de rondas creadas
        """
        try:
            self.logger.info(f"Generando calendario de liga para {competition.name}")
            
            if len(teams) < 2:
                raise ValueError("Se necesitan al menos 2 equipos")
            
            # Calcular número de jornadas
            n_teams = len(teams)
            total_rounds = (n_teams - 1) * (2 if competition.competition_format == "double_round" else 1)
            
            # Crear lista de IDs de equipos
            team_ids = [team.id for team in teams]
            
            # Algoritmo Round Robin
            def round_robin(ids, rounds):
                """Algoritmo Round Robin para generar emparejamientos"""
                if len(ids) % 2 != 0:
                    ids.append(None)
                
                n = len(ids)
                schedule = []
                
                for round_num in range(rounds):
                    round_matches = []
                    
                    for i in range(n // 2):
                        home = ids[i]
                        away = ids[n - 1 - i]
                        
                        if home is not None and away is not None:
                            # Alternar localía según ronda
                            if round_num % 2 == 0:
                                round_matches.append((home, away))
                            else:
                                round_matches.append((away, home))
                    
                    # Rotar equipos
                    ids.insert(1, ids.pop())
                    schedule.append(round_matches)
                
                return schedule
            
            # Generar calendario
            schedule = round_robin(team_ids, total_rounds)
            
            # Crear rondas en la base de datos
            created_rounds = []
            start_date = competition.start_date or datetime.now()
            
            for round_num, matches in enumerate(schedule, 1):
                # Crear ronda
                round_obj = Round(
                    competition_id=competition.id,
                    name=f"Fecha {round_num}",
                    round_number=round_num,
                    round_type="regular",
                    start_date=start_date + timedelta(days=(round_num-1) * 7),
                    end_date=start_date + timedelta(days=(round_num-1) * 7 + 2),
                    is_completed=False
                )
                
                db.add(round_obj)
                db.flush()  # Para obtener el ID
                
                # Crear partidos de la ronda
                for match_num, (home_id, away_id) in enumerate(matches, 1):
                    # Encontrar objetos Team
                    home_team = next((t for t in teams if t.id == home_id), None)
                    away_team = next((t for t in teams if t.id == away_id), None)
                    
                    if not home_team or not away_team:
                        continue
                    
                    match_date = round_obj.start_date + timedelta(hours=16 + (match_num * 2))
                    
                    match_obj = Match(
                        competition_id=competition.id,
                        round_id=round_obj.id,
                        home_team_id=home_id,
                        away_team_id=away_id,
                        match_date=match_date,
                        stadium=home_team.stadium or "Estadio Principal",
                        city=home_team.city or "Ciudad",
                        status=MatchStatus.SCHEDULED.value
                    )
                    
                    db.add(match_obj)
                
                created_rounds.append(round_obj)
            
            db.commit()
            self.logger.info(f"Calendario generado: {len(created_rounds)} rondas creadas")
            return created_rounds
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error generando calendario: {str(e)}")
            raise
    
    def generate_group_stage(
        self,
        competition: Competition,
        teams: List[Team],
        db: Session
    ) -> List[Round]:
        """
        Genera fase de grupos
        """
        try:
            self.logger.info(f"Generando fase de grupos para {competition.name}")
            
            if competition.groups <= 0:
                raise ValueError("La competencia no está configurada para fase de grupos")
            
            # Distribuir equipos en grupos
            groups = {}
            teams_per_group = len(teams) // competition.groups
            
            for i in range(competition.groups):
                group_letter = chr(65 + i)  # A, B, C, ...
                start_idx = i * teams_per_group
                end_idx = start_idx + teams_per_group
                groups[group_letter] = teams[start_idx:end_idx]
            
            # Crear rondas por grupo
            created_rounds = []
            start_date = competition.start_date or datetime.now()
            round_counter = 1
            
            for group_letter, group_teams in groups.items():
                # Generar calendario dentro del grupo
                group_team_ids = [t.id for t in group_teams]
                group_rounds = (len(group_teams) - 1) * 2 
                
                for group_round_num in range(1, group_rounds + 1):
                    round_obj = Round(
                        competition_id=competition.id,
                        name=f"Grupo {group_letter} - Fecha {group_round_num}",
                        round_number=round_counter,
                        round_type="group_stage",
                        phase="group_stage",
                        phase_round=group_round_num,
                        group_letter=group_letter,
                        start_date=start_date + timedelta(days=(round_counter-1) * 3),
                        end_date=start_date + timedelta(days=(round_counter-1) * 3 + 2),
                        is_completed=False
                    )
                    
                    db.add(round_obj)
                    db.flush()
                    
                    # Aquí iría la lógica para generar partidos dentro del grupo
                    # Similar a generate_league_schedule pero solo con equipos del grupo
                    
                    created_rounds.append(round_obj)
                    round_counter += 1
            
            db.commit()
            return created_rounds
            
        except Exception as e:
            db.rollback()
            self.logger.error(f"Error generando fase de grupos: {str(e)}")
            raise
    
    def create_competition_template(
        self,
        template_name: str,
        total_teams: int,
        created_by: int
    ) -> Dict[str, Any]:
        """
        Crea plantillas predefinidas para competencias
        """
        templates = {
            "liga_20_equipos": {
                "name": "Liga Profesional",
                "description": "Liga de 20 equipos - Todos contra todos",
                "competition_type": CompetitionType.LEAGUE.value,
                "competition_format": CompetitionFormat.DOUBLE_ROUND.value,
                "total_teams": 20,
                "groups": 0,
                "teams_per_group": 0,
                "teams_to_qualify": 0,
                "promotion_spots": 0,
                "relegation_spots": 3,
                "international_spots": 4,
                "config": {
                    "phases": ["regular_season"],
                    "rounds_per_phase": {"regular_season": 38},
                    "teams_per_phase": {"regular_season": 20},
                    "has_relegation": True
                }
            },
            "copa_32_equipos": {
                "name": "Copa Nacional",
                "description": "Torneo eliminatorio de 32 equipos",
                "competition_type": CompetitionType.CUP.value,
                "competition_format": CompetitionFormat.HOME_AWAY.value,
                "total_teams": 32,
                "groups": 0,
                "teams_per_group": 0,
                "teams_to_qualify": 1,
                "promotion_spots": 0,
                "relegation_spots": 0,
                "international_spots": 0,
                "config": {
                    "phases": ["round_of_32", "round_of_16", "quarterfinals", "semifinals", "final"],
                    "is_double_match": False,
                    "has_third_place": False
                }
            },
            "liga_copa": {
                "name": "Liga + Playoff",
                "description": "Fase regular + eliminatoria",
                "competition_type": CompetitionType.LEAGUE_CUP.value,
                "competition_format": CompetitionFormat.DOUBLE_ROUND.value,
                "total_teams": total_teams,
                "groups": 0,
                "teams_per_group": 0,
                "teams_to_qualify": 8,
                "promotion_spots": 0,
                "relegation_spots": 2,
                "international_spots": 4,
                "config": {
                    "phases": ["regular_season", "playoff"],
                    "rounds_per_phase": {"regular_season": (total_teams - 1) * 2, "playoff": 3},
                    "teams_per_phase": {"regular_season": total_teams, "playoff": 8},
                    "is_double_match": True
                }
            }
        }
        
        if template_name not in templates:
            raise ValueError(f"Plantilla '{template_name}' no encontrada")
        
        template = templates[template_name].copy()
        
        # Ajustar total de equipos si es necesario
        if template_name == "liga_copa":
            template["total_teams"] = total_teams
            template["teams_to_qualify"] = min(8, total_teams // 2)
        
        return template