# backend/app/schemas/competition/competition.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Dict, Any
from datetime import datetime
from enum import Enum
from app.models.competition import CompetitionType, CompetitionFormat, CompetitionStatus

class CompetitionBase(BaseModel):
    name: str = Field(..., min_length=3, max_length=200)
    description: Optional[str] = None
    country: Optional[str] = None
    season: str = Field(..., min_length=4, max_length=20)
    logo_url: Optional[str] = None
    
    competition_type: CompetitionType
    competition_format: CompetitionFormat
    
    total_teams: int = Field(..., ge=2, le=100)
    groups: int = Field(0, ge=0, le=50)
    teams_per_group: int = Field(0, ge=0, le=100)
    
    teams_to_qualify: int = Field(0, ge=0)
    promotion_spots: int = Field(0, ge=0)
    relegation_spots: int = Field(0, ge=0)
    international_spots: int = Field(0, ge=0)
    
    config: Optional[Dict[str, Any]] = Field(default_factory=dict)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class CompetitionCreate(CompetitionBase):
    team_ids: Optional[List[int]] = Field(default_factory=list)
    
    @validator('config')
    def validate_config(cls, v):
        if v is None:
            return {}
        return v
    
    @validator('groups')
    def validate_groups(cls, v, values):
        if v > 0 and 'total_teams' in values:
            if values['total_teams'] % v != 0:
                raise ValueError('El número total de equipos debe ser divisible por el número de grupos')
        return v

class CompetitionUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=3, max_length=200)
    description: Optional[str] = None
    country: Optional[str] = None
    season: Optional[str] = Field(None, min_length=4, max_length=20)
    logo_url: Optional[str] = None
    
    competition_type: Optional[CompetitionType] = None
    competition_format: Optional[CompetitionFormat] = None
    
    total_teams: Optional[int] = Field(None, ge=2, le=100)
    groups: Optional[int] = Field(None, ge=0, le=50)
    teams_per_group: Optional[int] = Field(None, ge=0, le=100)
    
    teams_to_qualify: Optional[int] = Field(None, ge=0)
    promotion_spots: Optional[int] = Field(None, ge=0)
    relegation_spots: Optional[int] = Field(None, ge=0)
    international_spots: Optional[int] = Field(None, ge=0)
    
    config: Optional[Dict[str, Any]] = None
    status: Optional[CompetitionStatus] = None
    is_active: Optional[bool] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

    @validator('config')
    def validate_config(cls, v):
        if v is None:
            return {}
        return v

    @validator('groups')
    def validate_groups(cls, v, values):
        if v is None:
            return v
        total_teams = values.get('total_teams')
        if total_teams and v > 0 and total_teams % v != 0:
            raise ValueError('El número total de equipos debe ser divisible por el número de grupos')
        return v

class CompetitionResponse(CompetitionBase):
    id: int
    status: CompetitionStatus
    is_active: bool
    created_by: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CompetitionWithTeams(CompetitionResponse):
    teams: List[Any] = Field(default_factory=list)
    total_teams_registered: int = 0

class CompetitionTemplate(BaseModel):
    """Plantillas predefinidas para competencias"""
    name: str
    description: str
    competition_type: CompetitionType
    competition_format: CompetitionFormat
    total_teams: int
    groups: int
    teams_per_group: int
    teams_to_qualify: int
    promotion_spots: int
    relegation_spots: int
    international_spots: int
    config: Dict[str, Any]

class CompetitionStats(BaseModel):
    total_matches: int
    matches_played: int
    matches_scheduled: int
    matches_in_progress: int
    goals_scored: int
    avg_goals_per_match: float
    total_rounds: int
    completed_rounds: int
