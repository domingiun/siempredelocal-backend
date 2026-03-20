# backend/app/schemas/bet/Bet.py
from datetime import datetime
from typing import List
from pydantic import BaseModel
from .BetPrediction import BetPredictionCreate, BetPredictionRead

class BetBase(BaseModel):
    bet_date_id: int
    is_finalized: bool = False

class BetPredictionCreate(BaseModel):
    match_id: int
    predicted_home_score: int
    predicted_away_score: int

class BetCreate(BaseModel):
    bet_date_id: int
    predictions: List[BetPredictionCreate] 

class BetRead(BaseModel):
    id: int
    user_id: int
    bet_date_id: int
    points: int
    submitted_at: datetime
    predictions: List[BetPredictionRead]

    class Config:
        from_attributes = True
    
