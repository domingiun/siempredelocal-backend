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

class BetDateRead(BetDateBase):
    id: int
    match_count: int = 0 

    class Config:
        from_attributes = True
