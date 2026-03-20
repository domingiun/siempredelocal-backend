# backend/app/schemas/bet/BetPlan.py
from pydantic import BaseModel, computed_field

class BetPlanBase(BaseModel):
    name: str
    credits: int
    price_cop: int
    discount_percent: float = 0.0

class BetPlanCreate(BetPlanBase):
    pass

class BetPlanRead(BetPlanBase):
    id: int
    
    @computed_field
    @property
    def final_price(self) -> int:
        """Precio final con descuento"""
        return self.price_cop - int(self.price_cop * self.discount_percent / 100)
    
    @computed_field
    @property
    def prize_contribution(self) -> int:
        """Porción que va al premio"""
        return self.credits * 1950  
    
    @computed_field
    @property
    def profit(self) -> int:
        """Ganancia por plan"""
        return self.final_price - self.prize_contribution
    
    @computed_field
    @property
    def price_per_credit(self) -> float:
        """Precio por crédito"""
        return self.final_price / self.credits
    
    class Config:
        from_attributes = True