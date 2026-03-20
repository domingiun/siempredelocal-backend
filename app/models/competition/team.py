# backend/app/models/competitions/team.py
from sqlalchemy import Column, Integer, String, Text, Boolean, DateTime, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from sqlalchemy import UniqueConstraint
from app.db import Base

class Team(Base):
    __tablename__ = "teams"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    short_name = Column(String(50), nullable=True)
    country = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    stadium = Column(String(200), nullable=True)
        
    logo_url = Column(String(500), nullable=True)
    website = Column(String(200), nullable=True)
    
    # Estadísticas generales (se actualizan automáticamente)
    matches_played = Column(Integer, default=0)
    matches_won = Column(Integer, default=0)
    matches_drawn = Column(Integer, default=0)
    matches_lost = Column(Integer, default=0)
    
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    goal_difference = Column(Integer, default=0)
    
    points = Column(Integer, default=0)
    
    is_active = Column(Boolean, default=True)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # Relaciones
    competition_teams = relationship("CompetitionTeam", back_populates="team")
    home_matches = relationship("Match", foreign_keys="[Match.home_team_id]", back_populates="home_team")
    away_matches = relationship("Match", foreign_keys="[Match.away_team_id]", back_populates="away_team")
    
    def __repr__(self):
        return f"<Team {self.name}>"

class CompetitionTeam(Base):
    __tablename__ = "competition_teams"
    
    id = Column(Integer, primary_key=True, index=True)
    competition_id = Column(Integer, ForeignKey("competitions.id", ondelete="CASCADE"), nullable=False)
    team_id = Column(Integer, ForeignKey("teams.id", ondelete="CASCADE"), nullable=False)
    group_letter = Column(String(1), nullable=True)  # A, B, C, etc.
    group_position = Column(Integer, default=0)      # Posición en el grupo
    
    # Estadísticas en esta competencia
    matches_played = Column(Integer, default=0)
    matches_won = Column(Integer, default=0)
    matches_drawn = Column(Integer, default=0)
    matches_lost = Column(Integer, default=0)
    
    goals_for = Column(Integer, default=0)
    goals_against = Column(Integer, default=0)
    goal_difference = Column(Integer, default=0)
    
    points = Column(Integer, default=0)
    position = Column(Integer, default=0)  # Posición en la tabla general
    
    # Relaciones
    competition = relationship("Competition")
    team = relationship("Team", back_populates="competition_teams")
    
    # Restricción única
    __table_args__ = (
        UniqueConstraint('competition_id', 'team_id', name='uq_competition_team'),
    )
    
    def __repr__(self):
        return f"<CompetitionTeam {self.team.name} in {self.competition.name}>"