# backend/app/models/competition/round.py
from sqlalchemy import Column, Integer, String, Text, Enum, Boolean, DateTime, ForeignKey, event
from sqlalchemy.orm import relationship, validates
from sqlalchemy.sql import func
from app.db import Base
import enum
from datetime import datetime

class RoundType(str, enum.Enum):
    """Tipos de ronda"""
    REGULAR = "regular"
    GROUP_STAGE = "group_stage"
    ROUND_OF = "round_of"
    SEMIFINAL = "semifinal"
    FINAL = "final"
    THIRD_PLACE = "third_place"

class Round(Base):
    __tablename__ = "rounds"
    
    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    
    name = Column(String(100), nullable=False)
    round_number = Column(Integer, nullable=False)
    round_type = Column(Enum(RoundType, values_callable=lambda x: [e.value for e in x]), default=RoundType.REGULAR)
   
    # Para fases eliminatorias
    phase = Column(String(50), nullable=True)
    phase_round = Column(Integer, default=1)
    
    group_letter = Column(String(1), nullable=True)
    
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    
    is_completed = Column(Boolean, default=False)
    completed_at = Column(DateTime, nullable=True)
    
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 📌 RELACIONES MEJORADAS
    competition = relationship("Competition", back_populates="rounds")
    matches = relationship("Match", back_populates="round", cascade="all, delete-orphan")
    
    @validates('round_number')
    def validate_round_number(self, key, round_number):
        if round_number < 1:
            raise ValueError("El número de jornada debe ser mayor a 0")
        return round_number
    
    @validates('name')
    def validate_name(self, key, name):
        if len(name) < 2:
            raise ValueError("El nombre debe tener al menos 2 caracteres")
        return name
    
    def check_team_duplicates(self, db):
        """Verificar que no haya equipos duplicados en la jornada"""
        from app.models.competition.match import Match
        
        matches = db.query(Match).filter(
            Match.round_id == self.id,
            Match.competition_id == self.competition_id
        ).all()
        
        teams_in_round = set()
        for match in matches:
            if match.home_team_id:
                if match.home_team_id in teams_in_round:
                    return False, f"El equipo local {match.home_team_id} aparece más de una vez en esta jornada"
                teams_in_round.add(match.home_team_id)
            
            if match.away_team_id:
                if match.away_team_id in teams_in_round:
                    return False, f"El equipo visitante {match.away_team_id} aparece más de una vez en esta jornada"
                teams_in_round.add(match.away_team_id)
        
        return True, "OK"
    
    def update_completion_status(self, db, auto_complete=True):
        """Actualizar estado de completado basado en partidos"""
        from app.models.competition.match import Match, MatchStatus
        
        matches = db.query(Match).filter(
            Match.round_id == self.id,
            Match.competition_id == self.competition_id
        ).all()
        
        if not matches:
            self.is_completed = False
            self.completed_at = None
            return
        
        # Verificar si hay al menos un partido programado
        has_scheduled_matches = any(
            m.status == MatchStatus.SCHEDULED.value for m in matches
        )
        
        # Verificar si todos están finalizados
        all_finished = all(
            m.status == MatchStatus.FINISHED.value for m in matches
        )
        
        # Si hay partidos programados, la jornada está abierta
        if has_scheduled_matches:
            self.is_completed = False
            self.completed_at = None
        
        # Si auto_complete está activado y todos están finalizados, marcar como completada
        elif auto_complete and all_finished and not self.is_completed:
            self.is_completed = True
            self.completed_at = datetime.now()
        
        # Si no hay partidos programados pero no todos están finalizados, mantener estado actual
    
    def get_match_summary(self, db):
        """Obtener resumen de partidos de la jornada"""
        from app.models.competition.match import Match, MatchStatus
        
        matches = db.query(Match).filter(
            Match.round_id == self.id,
            Match.competition_id == self.competition_id
        ).all()
        
        total = len(matches)
        scheduled = len([m for m in matches if m.status == MatchStatus.SCHEDULED.value])
        in_progress = len([m for m in matches if m.status == MatchStatus.IN_PROGRESS.value])
        finished = len([m for m in matches if m.status == MatchStatus.FINISHED.value])
        cancelled = len([m for m in matches if m.status == MatchStatus.CANCELLED.value])
        
        return {
            "total": total,
            "scheduled": scheduled,
            "in_progress": in_progress,
            "finished": finished,
            "cancelled": cancelled,
            "teams_involved": self.get_teams_in_round(db)
        }
    
    def get_teams_in_round(self, db):
        """Obtener lista de equipos participantes en la jornada"""
        from app.models.competition.match import Match
        
        matches = db.query(Match).filter(
            Match.round_id == self.id,
            Match.competition_id == self.competition_id
        ).all()
        
        teams = set()
        for match in matches:
            if match.home_team_id:
                teams.add(match.home_team_id)
            if match.away_team_id:
                teams.add(match.away_team_id)
        
        return list(teams)
    
    def __repr__(self):
        return f"<Round {self.name} ({self.competition.name})>"