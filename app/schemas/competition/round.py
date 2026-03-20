# backend/app/schemas/competition/round.py
from pydantic import BaseModel, Field, validator
from typing import Optional, List, Any, Dict
from datetime import datetime
from app.models.competition.round import RoundType
from app.schemas.competition.match import MatchResponse

class RoundBase(BaseModel):
    name: str = Field(..., min_length=2, max_length=100)
    round_number: int = Field(..., ge=1)
    round_type: RoundType = Field(default=RoundType.REGULAR)
    phase: Optional[str] = None
    phase_round: int = Field(default=1, ge=1)
    group_letter: Optional[str] = Field(None, max_length=1)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None

class RoundCreate(RoundBase):
    generate_matches: bool = Field(default=True)

class RoundUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=2, max_length=100)
    round_type: Optional[RoundType] = None
    phase: Optional[str] = None
    phase_round: Optional[int] = Field(default=None, ge=1)
    group_letter: Optional[str] = Field(None, max_length=1)
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_completed: Optional[bool] = None

class RoundResponse(BaseModel):
    id: int
    competition_id: int
    name: str
    round_number: int
    round_type: str 
    phase: Optional[str] = None
    phase_round: Optional[int] = None
    group_letter: Optional[str] = None
    start_date: Optional[datetime] = None
    end_date: Optional[datetime] = None
    is_completed: bool
    completed_at: Optional[datetime] = None
    created_at: datetime
    updated_at: datetime
    total_matches: Optional[int] = 0 
    matches_played: Optional[int] = 0
    competition_name: Optional[str] = None
    summary: Optional[Dict[str, Any]] = None
    teams_involved: Optional[List[int]] = None
    
    class Config:
        from_attributes = True

class RoundWithMatches(RoundResponse):
    matches: List[MatchResponse] = Field(default_factory=list)
    total_matches: int = 0
    matches_played: int = 0
    teams_involved: List[int] = Field(default_factory=list)
    match_summary: Dict[str, Any] = Field(default_factory=dict)
    
    class Config:
        from_attributes = True

class RoundValidation(BaseModel):
    round_id: int
    round_name: str
    total_matches: int
    validations: List[Dict[str, Any]]
    is_valid: bool
