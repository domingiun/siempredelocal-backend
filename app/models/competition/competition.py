# backend/app/models/competitions/competitions.py
from sqlalchemy import Column, Integer, String, Text, Enum, Boolean, DateTime, JSON
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import enum

class CompetitionType(str, enum.Enum):
    LEAGUE = "league"
    CUP = "cup"
    LEAGUE_CUP = "league_cup"
    GROUPS_PLAYOFF = "groups_playoff"

class CompetitionFormat(str, enum.Enum):
    """Formatos de competencia"""
    SINGLE_ROUND = "single_round"
    DOUBLE_ROUND = "double_round"
    HOME_AWAY = "home_away"

class CompetitionStatus(str, enum.Enum):
    DRAFT = "draft"
    SCHEDULED = "scheduled"
    ONGOING = "ongoing"
    COMPLETED = "completed"
    CANCELLED = "cancelled"

class Competition(Base):
    __tablename__ = "competitions"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(200), nullable=False, index=True)
    description = Column(Text, nullable=True)
    country = Column(String(100), nullable=True)
    season = Column(String(50), nullable=False)
    
    # Configuración de competencia (USANDO ENUM CORRECTAMENTE)
    competition_type = Column(Enum(CompetitionType, values_callable=lambda x: [e.value for e in x]),nullable=False)
    competition_format = Column(Enum(CompetitionFormat,values_callable=lambda x: [e.value for e in x]),nullable=False)

    # Estructura
    total_teams = Column(Integer, nullable=False)
    groups = Column(Integer, default=0)
    teams_per_group = Column(Integer, default=0)
    
    # Clasificación
    teams_to_qualify = Column(Integer, default=0)
    promotion_spots = Column(Integer, default=0)
    relegation_spots = Column(Integer, default=0)
    international_spots = Column(Integer, default=0)
    
    # Configuración avanzada
    config = Column(JSON, default={
        "phases": [],
        "rounds_per_phase": {},
        "teams_per_phase": {},
        "is_double_match": False,
        "has_third_place": False,
        "best_third_qualify": False,
    })
    
    # Estado
    status = Column(Enum(CompetitionStatus, values_callable=lambda x: [e.value for e in x]), default=CompetitionStatus.DRAFT)
    is_active = Column(Boolean, default=True)
    start_date = Column(DateTime, nullable=True)
    end_date = Column(DateTime, nullable=True)
    logo_url = Column(String(255), nullable=True)
    
    # Auditoría
    created_by = Column(Integer, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    # 📌 RELACIONES COMPLETAS
    rounds = relationship("Round", back_populates="competition", cascade="all, delete-orphan")
    competition_teams = relationship("CompetitionTeam", back_populates="competition", cascade="all, delete-orphan")
    matches = relationship("Match", back_populates="competition", cascade="all, delete-orphan")
    
    def __repr__(self):
        return f"<Competition {self.name} ({self.season})>"
