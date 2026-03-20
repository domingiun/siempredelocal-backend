# backend/app/models/bet/BetPlan.py
from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean
from app.db import Base
from datetime import datetime

class BetPlan(Base):
    __tablename__ = "bet_plans"
    
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String(100), unique=True, nullable=False)
    credits = Column(Integer, nullable=False)
    price_cop = Column(Integer, nullable=False)
    discount_percent = Column(Float, default=0.0)
    prize_contribution = Column(Integer, default=1950)
    created_at = Column(DateTime, default=datetime.now)
    is_active = Column(Boolean, default=True)
    
    @property
    def final_price(self) -> int:
        """Calcula el precio final con descuento"""
        discount = self.discount_percent or 0
        discount_amount = int(self.price_cop * discount / 100)
        return self.price_cop - discount_amount
    
    @property
    def final_price_calc(self) -> int:
        """Alias para final_price (para compatibilidad con frontend)"""
        return self.final_price
    
    @property
    def profit(self) -> int:
        """Calcula la ganancia (precio final - contribución al premio)"""
        contribution = self.prize_contribution or 1950
        return self.final_price - contribution
    
    @property
    def price_per_credit(self) -> float:
        """Precio por crédito individual"""
        if self.credits > 0:
            return self.final_price / self.credits
        return 0.0
    
    @property
    def base_price(self) -> int:
        """Alias para compatibilidad con frontend"""
        return self.price_cop
    
    def __repr__(self):
        return f"<BetPlan(id={self.id}, name='{self.name}', credits={self.credits}, price_cop={self.price_cop})>"