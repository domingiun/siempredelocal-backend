# backend/app/schemas/bet/BetDate.py
from datetime import datetime
from typing import List, Optional
from pydantic import BaseModel

class BetDateBase(BaseModel):
    name: str
    start_datetime: datetime
    status: str = "open"
    prize_cop: int = 0
    accumulated_prize: int = 0
    close_datetime: Optional[datetime] = None
    required_credits: int = 1

class BetDateCreate(BetDateBase):
    match_ids: list[int]  

class MatchBrief(BaseModel):
    id: int
    home_team_name: Optional[str] = None
    away_team_name: Optional[str] = None
    match_date: Optional[datetime] = None
    competition_name: Optional[str] = None

    class Config:
        from_attributes = True

class BetDateRead(BetDateBase):
    id: int
    match_count: int = 0
    bet_count: int = 0
    matches: List[MatchBrief] = []

    class Config:
        from_attributes = True
