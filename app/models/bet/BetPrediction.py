# backend/app/models/bet/BetPrediction.py - Mejorado
from sqlalchemy import Column, Integer, ForeignKey, Computed
from sqlalchemy.orm import relationship
from app.db import Base

class BetPrediction(Base):
    __tablename__ = "bet_predictions"
    
    id = Column(Integer, primary_key=True)
    bet_id = Column(Integer, ForeignKey("bets.id"))
    match_id = Column(Integer, ForeignKey("matches.id"))
    predicted_home_score = Column(Integer)
    predicted_away_score = Column(Integer)
    points = Column(Integer, default=0)
    
    bet = relationship("Bet", back_populates="predictions")
    match = relationship("Match")
    
    def calculate_match_points(self):
        """Calcular puntos para esta predicción"""
        if not self.match or not self.match.is_finished:
            return 0
        
        # Acierto exacto
        if (self.predicted_home_score == self.match.home_score and 
            self.predicted_away_score == self.match.away_score):
            return 3
        
        # Acierto ganador
        predicted_winner = self.get_predicted_winner()
        actual_winner = self.match.winner
        
        if predicted_winner == actual_winner:
            return 1
        
        return 0
    
    def get_predicted_winner(self):
        """Determinar ganador según predicción"""
        if self.predicted_home_score > self.predicted_away_score:
            return "home"
        elif self.predicted_away_score > self.predicted_home_score:
            return "away"
        return "draw"
    
    def _get_actual_winner(self):
        """Determinar ganador real del partido"""
        if not self.match or not self.match.is_finished:
            return None
        
        if self.match.home_score > self.match.away_score:
            return "home"
        elif self.match.away_score > self.match.home_score:
            return "away"
        return "draw"
    
    def update_points(self):
        """Actualizar puntos basados en cálculo actual"""
        self.points = self.calculate_match_points()
        return self.points