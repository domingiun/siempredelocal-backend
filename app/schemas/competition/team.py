# backend/app/schemas/competition/team.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List
from datetime import datetime

class TeamBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=200)
    short_name: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = None
    city: Optional[str] = None
    stadium: Optional[str] = None
    logo_url: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = Field(None, max_length=200)

class TeamCreate(TeamBase):
    pass

class AddTeamsToCompetitionRequest(BaseModel):
    team_ids: List[int]

class TeamUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=200)
    short_name: Optional[str] = Field(None, max_length=50)
    country: Optional[str] = None
    city: Optional[str] = None
    stadium: Optional[str] = None
    logo_url: Optional[str] = Field(None, max_length=500)
    website: Optional[str] = Field(None, max_length=200)
    is_active: Optional[bool] = None

class TeamResponse(TeamBase):
    id: int
    matches_played: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    logo_url: str | None
    points: int
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True

class CompetitionTeamCreate(BaseModel):
    team_id: int
    group_letter: Optional[str] = Field(None, max_length=1)
    group_position: Optional[int] = Field(0, ge=0)

class CompetitionTeamResponse(BaseModel):
    id: int
    competition_id: int
    team_id: int
    team: TeamResponse
    group_letter: Optional[str]
    group_position: int
    matches_played: int
    matches_won: int
    matches_drawn: int
    matches_lost: int
    goals_for: int
    goals_against: int
    goal_difference: int
    points: int
    position: int
    
    class Config:
        from_attributes = True