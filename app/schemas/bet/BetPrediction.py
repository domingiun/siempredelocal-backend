# backend/app/schemas/bet/BetPrediction.py
from pydantic import BaseModel

class BetPredictionBase(BaseModel):
    match_id: int
    predicted_home_score: int
    predicted_away_score: int

class BetPredictionCreate(BetPredictionBase):
    pass

class BetPredictionRead(BetPredictionBase):
    id: int
    points: int

    class Config:
        from_attributes = True
