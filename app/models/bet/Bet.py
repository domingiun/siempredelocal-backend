# backend/app/models/bet/Bet.py - Añadir métodos
from sqlalchemy import Column, Integer, ForeignKey, DateTime, Boolean
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base

class Bet(Base):
    __tablename__ = "bets"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    bet_date_id = Column(Integer, ForeignKey("betdates.id"))
    points = Column(Integer, default=0)
    submitted_at = Column(DateTime, default=func.now())
    is_finalized = Column(Boolean, default=False)
    rank = Column(Integer, nullable=True)
    
    user = relationship("User", back_populates="bets")
    bet_date = relationship("BetDate", back_populates="bets")
    predictions = relationship("BetPrediction", back_populates="bet", cascade="all, delete-orphan")
    
    def get_ranking_info(self):
        """Obtener información para ranking"""
        correct_picks = 0

        for prediction in self.predictions:
            if prediction.points > 0:
                correct_picks += 1

        return {
            "user_id": self.user_id,
            "user_name": self.user.username if self.user else "Usuario",
            "points": self.points,
            "correct_picks": correct_picks,
            "rank": self.rank
        }