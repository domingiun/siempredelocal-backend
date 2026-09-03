# backend/app/schemas/bet/BetPrediction.py
from typing import Optional
from pydantic import BaseModel

class BetPredictionBase(BaseModel):
    match_id: int
    predicted_home_score: Optional[int] = None
    predicted_away_score: Optional[int] = None
    predicted_result: Optional[str] = None

class BetPredictionCreate(BetPredictionBase):
    pass

class BetPredictionRead(BetPredictionBase):
    id: int
    points: int

    class Config:
        from_attributes = True
