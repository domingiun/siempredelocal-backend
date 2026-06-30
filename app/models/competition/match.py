# backend/app/models/competition/match.py
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Enum
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import enum

# MIGRACIÓN: Si la tabla ya existe, ejecutar en Railway/producción:
# ALTER TABLE matches ADD COLUMN IF NOT EXISTS api_fixture_id INTEGER;
# ALTER TABLE matches ADD COLUMN IF NOT EXISTS api_synced_at TIMESTAMP;

class MatchStatus(str, enum.Enum):
    """Estados del partido"""
    SCHEDULED = "Programado"
    IN_PROGRESS = "En curso" 
    FINISHED = "Finalizado"
    CANCELLED = "Cancelado"
    POSTPONED = "Aplazado"

class Match(Base):
    __tablename__ = "matches"
    
    # Identificación
    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    round_id = Column(Integer, ForeignKey("rounds.id", ondelete="CASCADE"), nullable=False)
        
    # Equipos
    home_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    away_team_id = Column(Integer, ForeignKey("teams.id"), nullable=False)
    
    # Información básica
    match_date = Column(DateTime, nullable=False, index=True)
    stadium = Column(String(200), nullable=True)
    city = Column(String(100), nullable=True)
    
    # Resultado
    home_score = Column(Integer, default=0)
    away_score = Column(Integer, default=0)
    penalty_home = Column(Integer, nullable=True)   # marcador en penaltis (None si no hubo)
    penalty_away = Column(Integer, nullable=True)
    status = Column(Enum(MatchStatus, values_callable=lambda x: [e.value for e in x]),
    default=MatchStatus.SCHEDULED
)
    
    # Integración api-football
    api_fixture_id = Column(Integer, nullable=True, index=True, unique=True)
    api_synced_at  = Column(DateTime, nullable=True)

    # Auditoría
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relaciones
    competition = relationship("Competition")
    round = relationship("Round", back_populates="matches")
    home_team = relationship("Team", foreign_keys=[home_team_id])
    away_team = relationship("Team", foreign_keys=[away_team_id])
    bet_dates = relationship(
    "BetDate",
    secondary="bet_date_matches",
    back_populates="matches",
    overlaps="matches"
)
    
    def __repr__(self):
        return f"<Match {self.home_team.name} {self.home_score}-{self.away_score} {self.away_team.name}>"
    
    @property
    def is_finished(self):
        """Verifica si el partido está finalizado"""
        return self.status == MatchStatus.FINISHED.value
    
    @property
    def winner(self):
        """Devuelve el ganador o None si es empate"""
        if not self.is_finished:
            return None
        if self.home_score > self.away_score:
            return "home"
        elif self.away_score > self.home_score:
            return "away"
        return "draw"
