from datetime import date, datetime, time
from typing import List, Optional, Tuple

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import and_, func
from sqlalchemy.orm import Session

from app.constants.bet_constants import PRIZE_CONTRIBUTION_PER_CREDIT, PROFIT_PER_CREDIT
from app.core.dependencies import get_current_admin_user
from app.db import get_db
from app.models.bet.BetDate import BetDate
from app.models.bet.BetPlan import BetPlan
from app.models.bet.UserWallet import UserWallet
from app.models.bet.transaction import Transaction, TransactionStatus, TransactionType
from app.models.user.user import User
from app.schemas.bet.financial import (
    FinancialSummaryResponse,
    PlanSalesSummary,
    ResetAccumulatedPrizeResponse,
    UserCreditsSummary,
    UserCreditsSummaryResponse,
)

router = APIRouter(prefix="/financial", tags=["Financial"])


def _build_period_filters(
    start_date: Optional[date],
    end_date: Optional[date],
) -> Tuple[list, Optional[datetime], Optional[datetime]]:
    filters = [Transaction.status == TransactionStatus.COMPLETED]

    start_dt = None
    end_dt = None

    if start_date:
        start_dt = datetime.combine(start_date, time.min)
        filters.append(Transaction.created_at >= start_dt)

    if end_date:
        end_dt = datetime.combine(end_date, time.max)
        filters.append(Transaction.created_at <= end_dt)

    return filters, start_dt, end_dt


def _query_financial_summary(
    session: Session,
    start_date: Optional[date] = None,
    end_date: Optional[date] = None,
) -> FinancialSummaryResponse:
    base_filters, _, _ = _build_period_filters(start_date=start_date, end_date=end_date)
    purchase_filters = [*base_filters, Transaction.transaction_type == TransactionType.CREDIT_PURCHASE]
    usage_filters = [*base_filters, Transaction.transaction_type == TransactionType.BET_PLACEMENT]
    prize_filters = [*base_filters, Transaction.transaction_type == TransactionType.PRIZE_WIN]
    admin_adjustment_filters = [*base_filters, Transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT]

    prize_per_credit_expr = func.coalesce(BetPlan.prize_contribution, PRIZE_CONTRIBUTION_PER_CREDIT)
    prize_total_expr = Transaction.amount_credits * prize_per_credit_expr

    totals = (
        session.query(
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount_credits), 0),
            func.coalesce(func.sum(Transaction.amount_cop), 0),
            func.coalesce(func.sum(prize_total_expr), 0),
        )
        .outerjoin(
            BetPlan,
            and_(
                Transaction.reference_id == BetPlan.id,
                Transaction.reference_type == "bet_plan",
            ),
        )
        .filter(*purchase_filters)
        .one()
    )

    usage_totals = (
        session.query(
            func.coalesce(func.sum(Transaction.amount_credits), 0),
            func.coalesce(func.sum(Transaction.amount_cop), 0),
        )
        .filter(*usage_filters)
        .one()
    )

    prizes_paid_cop = (
        session.query(func.coalesce(func.sum(Transaction.amount_cop), 0))
        .filter(*prize_filters)
        .scalar()
        or 0
    )

    withdrawals_cop = (
        session.query(func.coalesce(func.sum(func.abs(Transaction.amount_cop)), 0))
        .filter(*admin_adjustment_filters)
        .filter(Transaction.reference_type == "withdrawal")
        .scalar()
        or 0
    )

    points_to_credits_cop = (
        session.query(func.coalesce(func.sum(func.abs(Transaction.amount_cop)), 0))
        .filter(*admin_adjustment_filters)
        .filter(Transaction.reference_type == "points_to_credits")
        .scalar()
        or 0
    )

    plan_rows = (
        session.query(
            BetPlan.id,
            BetPlan.name,
            func.count(Transaction.id),
            func.coalesce(func.sum(Transaction.amount_credits), 0),
            func.coalesce(func.sum(Transaction.amount_cop), 0),
            func.coalesce(func.sum(prize_total_expr), 0),
        )
        .join(
            BetPlan,
            and_(
                Transaction.reference_id == BetPlan.id,
                Transaction.reference_type == "bet_plan",
            ),
        )
        .filter(*purchase_filters)
        .group_by(BetPlan.id, BetPlan.name)
        .order_by(BetPlan.name.asc())
        .all()
    )

    total_packages_sold, total_credits_sold, total_revenue_cop, _ = totals
    total_credits_used, total_prize_pool_cop = usage_totals
    total_app_pool_cop = int(total_credits_used or 0) * int(PROFIT_PER_CREDIT)
    total_canjes_cop = int(withdrawals_cop) + int(points_to_credits_cop)

    plans: List[PlanSalesSummary] = []
    for row in plan_rows:
        plan_id, plan_name, packages_sold, credits_sold, revenue_cop, prize_pool_cop = row
        plans.append(
            PlanSalesSummary(
                plan_id=plan_id,
                plan_name=plan_name,
                packages_sold=int(packages_sold),
                total_credits_sold=int(credits_sold),
                total_revenue_cop=int(revenue_cop),
                total_prize_pool_cop=int(prize_pool_cop),
                total_app_pool_cop=int(revenue_cop) - int(prize_pool_cop),
            )
        )

    return FinancialSummaryResponse(
        start_date=start_date,
        end_date=end_date,
        total_packages_sold=int(total_packages_sold or 0),
        total_credits_sold=int(total_credits_sold or 0),
        total_credits_used=int(total_credits_used or 0),
        total_revenue_cop=int(total_revenue_cop or 0),
        total_prize_pool_cop=int(total_prize_pool_cop or 0),
        total_app_pool_cop=int(total_app_pool_cop or 0),
        total_prizes_paid_cop=int(prizes_paid_cop or 0),
        total_canjes_cop=int(total_canjes_cop or 0),
        total_withdrawals_cop=int(withdrawals_cop or 0),
        total_points_to_credits_cop=int(points_to_credits_cop or 0),
        plans=plans,
    )


@router.get("/summary/general", response_model=FinancialSummaryResponse)
def get_general_financial_summary(
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    return _query_financial_summary(session=session)


@router.get("/summary/range", response_model=FinancialSummaryResponse)
def get_financial_summary_by_range(
    start_date: date = Query(..., description="Fecha inicial en formato YYYY-MM-DD"),
    end_date: date = Query(..., description="Fecha final en formato YYYY-MM-DD"),
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date no puede ser mayor que end_date")

    return _query_financial_summary(
        session=session,
        start_date=start_date,
        end_date=end_date,
    )


@router.post("/accumulated-prize/reset/{bet_date_id}", response_model=ResetAccumulatedPrizeResponse)
def reset_accumulated_prize(
    bet_date_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    bet_date = session.query(BetDate).filter(BetDate.id == bet_date_id).first()
    if not bet_date:
        raise HTTPException(status_code=404, detail="Fecha de pronósticos no encontrada")

    previous = int(bet_date.accumulated_prize or 0)
    bet_date.accumulated_prize = 0
    session.commit()

    return ResetAccumulatedPrizeResponse(
        bet_date_id=bet_date.id,
        bet_date_name=bet_date.name,
        previous_accumulated_prize=previous,
        new_accumulated_prize=0,
        reset_at=datetime.now(),
        message="Premio acumulado reiniciado correctamente.",
    )


@router.get("/users-credits-summary", response_model=UserCreditsSummaryResponse)
def get_users_credits_summary(
    start_date: Optional[date] = Query(None, description="Fecha inicial YYYY-MM-DD"),
    end_date: Optional[date] = Query(None, description="Fecha final YYYY-MM-DD"),
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user),
):
    if start_date and end_date and start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date no puede ser mayor que end_date")

    base_usage_filters = [
        Transaction.transaction_type == TransactionType.BET_PLACEMENT,
        Transaction.status == TransactionStatus.COMPLETED,
    ]
    if start_date:
        base_usage_filters.append(Transaction.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        base_usage_filters.append(Transaction.created_at <= datetime.combine(end_date, time.max))

    usage_rows = (
        session.query(
            Transaction.user_id,
            func.coalesce(func.sum(Transaction.amount_credits), 0),
        )
        .filter(*base_usage_filters)
        .group_by(Transaction.user_id)
        .all()
    )
    used_by_user = {int(user_id): int(used or 0) for user_id, used in usage_rows}

    invest_filters = [
        Transaction.transaction_type == TransactionType.CREDIT_PURCHASE,
        Transaction.status == TransactionStatus.COMPLETED,
    ]
    if start_date:
        invest_filters.append(Transaction.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        invest_filters.append(Transaction.created_at <= datetime.combine(end_date, time.max))

    invested_rows = (
        session.query(
            Transaction.user_id,
            func.coalesce(func.sum(Transaction.amount_cop), 0),
        )
        .filter(*invest_filters)
        .group_by(Transaction.user_id)
        .all()
    )
    invested_by_user = {int(user_id): int(total or 0) for user_id, total in invested_rows}

    prize_filters = [
        Transaction.transaction_type == TransactionType.PRIZE_WIN,
        Transaction.status == TransactionStatus.COMPLETED,
    ]
    if start_date:
        prize_filters.append(Transaction.created_at >= datetime.combine(start_date, time.min))
    if end_date:
        prize_filters.append(Transaction.created_at <= datetime.combine(end_date, time.max))

    prizes_rows = (
        session.query(
            Transaction.user_id,
            func.coalesce(func.sum(Transaction.amount_cop), 0),
        )
        .filter(*prize_filters)
        .group_by(Transaction.user_id)
        .all()
    )
    prizes_by_user = {int(user_id): int(total or 0) for user_id, total in prizes_rows}

    users = (
        session.query(User, UserWallet)
        .outerjoin(UserWallet, UserWallet.user_id == User.id)
        .filter(User.is_active == True)  # noqa: E712
        .order_by(User.id.asc())
        .all()
    )

    response_users: List[UserCreditsSummary] = []
    for user, wallet in users:
        response_users.append(
            UserCreditsSummary(
                user_id=user.id,
                username=user.username,
                full_name=user.full_name,
                avatar_url=user.avatar_url,
                credits_used=used_by_user.get(user.id, 0),
                credits_available=int(wallet.credits if wallet else 0),
                total_invested_cop=invested_by_user.get(user.id, 0),
                total_prizes_cop=prizes_by_user.get(user.id, 0),
            )
        )

    return UserCreditsSummaryResponse(
        start_date=start_date,
        end_date=end_date,
        users=response_users,
    )
