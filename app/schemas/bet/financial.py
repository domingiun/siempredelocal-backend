from datetime import date, datetime
from typing import List, Optional
from pydantic import BaseModel, Field


class PlanSalesSummary(BaseModel):
    plan_id: int
    plan_name: str
    packages_sold: int = Field(description="Cantidad de recargas completadas para el plan")
    total_credits_sold: int
    total_revenue_cop: int
    total_prize_pool_cop: int
    total_app_pool_cop: int


class FinancialSummaryResponse(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    total_packages_sold: int
    total_credits_sold: int
    total_credits_used: int = 0
    total_revenue_cop: int
    total_prize_pool_cop: int
    total_app_pool_cop: int
    total_prizes_paid_cop: int = 0
    total_canjes_cop: int = 0
    total_withdrawals_cop: int = 0
    total_points_to_credits_cop: int = 0
    plans: List[PlanSalesSummary]


class ResetAccumulatedPrizeResponse(BaseModel):
    bet_date_id: int
    bet_date_name: str
    previous_accumulated_prize: int
    new_accumulated_prize: int
    reset_at: datetime
    message: str


class UserCreditsSummary(BaseModel):
    user_id: int
    username: str
    full_name: Optional[str] = None
    avatar_url: Optional[str] = None
    credits_used: int = 0
    credits_available: int = 0
    credits_used_last_betdate: int = 0
    total_invested_cop: int = 0
    total_prizes_cop: int = 0


class UserCreditsSummaryResponse(BaseModel):
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    last_betdate_name: Optional[str] = None
    users: List[UserCreditsSummary]
