# backend/app/services/competition_sync_service.py
from datetime import datetime
from sqlalchemy.orm import Session
from app.models.competition.match import Match, MatchStatus
from app.models.competition.round import Round
from app.models.competition.competition import Competition, CompetitionStatus
from app.services.standings_service import recalculate_competition_standings

def sync_after_match_update(match: Match, db: Session):
    """
    Sincroniza todos los elementos después de actualizar un partido
    """
    competition_id = match.competition_id
    
    # 1. Recalcular tabla de posiciones si el partido está finalizado
    if match.status == MatchStatus.FINISHED.value:
        recalculate_competition_standings(competition_id, db)
        print(f"✅ Tabla recalculada para competencia {competition_id}")
    
    # 2. Verificar si la jornada está completa
    round_matches = db.query(Match).filter(
        Match.round_id == match.round_id
    ).all()
    
    round_obj = db.query(Round).filter(Round.id == match.round_id).first()
    if round_obj:
        # Contar partidos finalizados o cancelados
        completed_matches = [
            m for m in round_matches 
            if m.status in [MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value]
        ]
        
        # Marcar jornada como completada si todos los partidos están finalizados/cancelados
        if len(completed_matches) == len(round_matches) and len(round_matches) > 0:
            if not round_obj.is_completed:
                round_obj.is_completed = True
                round_obj.completed_at = datetime.now()
                print(f"✅ Jornada {round_obj.name} marcada como completada")
        else:
            if round_obj.is_completed:
                round_obj.is_completed = False
                round_obj.completed_at = None
                print(f"⚠️  Jornada {round_obj.name} marcada como incompleta")
        
        db.commit()
    
    # 3. Verificar si la competencia está completa
    competition = db.query(Competition).filter(Competition.id == competition_id).first()
    if competition:
        # Contar rondas completadas
        total_rounds = db.query(Round).filter(Round.competition_id == competition_id).count()
        completed_rounds = db.query(Round).filter(
            Round.competition_id == competition_id,
            Round.is_completed == True
        ).count()
        
        # Marcar competencia como completada si todas las rondas están completadas
        if total_rounds > 0 and completed_rounds == total_rounds:
            if competition.status != CompetitionStatus.COMPLETED:
                competition.status = CompetitionStatus.COMPLETED
                competition.end_date = datetime.now()
                print(f"🏆 Competencia {competition.name} marcada como completada")
        elif competition.status == CompetitionStatus.COMPLETED:
            # Si estaba completada pero ahora no, cambiar a EN CURSO
            competition.status = CompetitionStatus.ONGOING
            print(f"🔄 Competencia {competition.name} cambiada a EN CURSO")
        
        db.commit()
    
    # 4. Actualizar estadísticas de equipos
    update_team_statistics(match, db)

def update_team_statistics(match: Match, db: Session):
    """
    Actualiza estadísticas generales de los equipos
    """
    from app.models.competition.team import Team
    
    if match.status != MatchStatus.FINISHED.value:
        return
    
    # Obtener equipos
    home_team = db.query(Team).filter(Team.id == match.home_team_id).first()
    away_team = db.query(Team).filter(Team.id == match.away_team_id).first()
    
    if not home_team or not away_team:
        return
    
    # Reiniciar estadísticas para recalcular
    home_team.matches_played = 0
    home_team.matches_won = 0
    home_team.matches_drawn = 0
    home_team.matches_lost = 0
    home_team.goals_for = 0
    home_team.goals_against = 0
    home_team.points = 0
    
    away_team.matches_played = 0
    away_team.matches_won = 0
    away_team.matches_drawn = 0
    away_team.matches_lost = 0
    away_team.goals_for = 0
    away_team.goals_against = 0
    away_team.points = 0
    
    # Obtener todos los partidos finalizados de ambos equipos
    home_matches = db.query(Match).filter(
        (Match.home_team_id == home_team.id) | (Match.away_team_id == home_team.id),
        Match.status == MatchStatus.FINISHED
    ).all()
    
    away_matches = db.query(Match).filter(
        (Match.home_team_id == away_team.id) | (Match.away_team_id == away_team.id),
        Match.status == MatchStatus.FINISHED
    ).all()
    
    # Procesar partidos del equipo local
    for m in home_matches:
        is_home = m.home_team_id == home_team.id
        home_team.matches_played += 1
        
        if is_home:
            home_team.goals_for += m.home_score or 0
            home_team.goals_against += m.away_score or 0
            
            if (m.home_score or 0) > (m.away_score or 0):
                home_team.matches_won += 1
                home_team.points += 3
            elif (m.home_score or 0) < (m.away_score or 0):
                home_team.matches_lost += 1
            else:
                home_team.matches_drawn += 1
                home_team.points += 1
        else:
            home_team.goals_for += m.away_score or 0
            home_team.goals_against += m.home_score or 0
            
            if (m.away_score or 0) > (m.home_score or 0):
                home_team.matches_won += 1
                home_team.points += 3
            elif (m.away_score or 0) < (m.home_score or 0):
                home_team.matches_lost += 1
            else:
                home_team.matches_drawn += 1
                home_team.points += 1
    
    # Procesar partidos del equipo visitante
    for m in away_matches:
        is_home = m.home_team_id == away_team.id
        away_team.matches_played += 1
        
        if is_home:
            away_team.goals_for += m.home_score or 0
            away_team.goals_against += m.away_score or 0
            
            if (m.home_score or 0) > (m.away_score or 0):
                away_team.matches_won += 1
                away_team.points += 3
            elif (m.home_score or 0) < (m.away_score or 0):
                away_team.matches_lost += 1
            else:
                away_team.matches_drawn += 1
                away_team.points += 1
        else:
            away_team.goals_for += m.away_score or 0
            away_team.goals_against += m.home_score or 0
            
            if (m.away_score or 0) > (m.home_score or 0):
                away_team.matches_won += 1
                away_team.points += 3
            elif (m.away_score or 0) < (m.home_score or 0):
                away_team.matches_lost += 1
            else:
                away_team.matches_drawn += 1
                away_team.points += 1
    
    # Calcular diferencia de goles
    home_team.goal_difference = home_team.goals_for - home_team.goals_against
    away_team.goal_difference = away_team.goals_for - away_team.goals_against
    
    db.commit()