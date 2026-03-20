# backend/app/routes/bet/pricing.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from typing import List, Dict, Any
from app.db import get_db
from app.constants.bet_constants import (
    CREDIT_PRICE_COP,
    PRIZE_CONTRIBUTION_PER_CREDIT,
    PROFIT_PER_CREDIT,
    REQUIRED_CREDITS_PER_BET,
    MIN_POINTS_TO_WIN,
    CREDIT_TO_CASH_RATE,
    WITHDRAWAL_FEE_PERCENT,
    MIN_WITHDRAWAL_AMOUNT,
    MAX_WITHDRAWAL_AMOUNT,
    WITHDRAWAL_PROCESSING_HOURS,
    TAX_PERCENTAGE,
    APPLY_TAXES,
    calculate_plan_details,
    get_all_plans_details,
    get_best_value_plan,
    PLANS_CONFIG
)
from app.schemas.bet.pricing import (
    CreditPricingRead,
    ConversionRatesRead,
    ConversionExample,
    PlanDetailRead,
    ProfitCalculationRequest,
    ProfitCalculationResponse,
    PlansComparisonResponse,
    PlanComparison,
    FinancialSummary,
    PriceConfiguration
)
from app.models.bet.transaction import Transaction, TransactionType
from app.models.bet.Bet import Bet
from app.models.user.user import User
from app.models.bet.UserWallet import UserWallet
from datetime import datetime, timedelta

router = APIRouter(prefix="/pricing", tags=["Pricing"])


@router.get("/credit-info", response_model=CreditPricingRead)
def get_credit_pricing_info():
    """Obtener información de precios de créditos"""
    return CreditPricingRead(
        credit_price_cop=CREDIT_PRICE_COP,
        prize_contribution_per_credit=PRIZE_CONTRIBUTION_PER_CREDIT,
        profit_per_credit=PROFIT_PER_CREDIT,
        required_credits_per_bet=REQUIRED_CREDITS_PER_BET,
        min_points_to_win=MIN_POINTS_TO_WIN,
        max_predictions_per_bet=10
    )


@router.get("/conversion-rates", response_model=ConversionRatesRead)
def get_conversion_rates():
    """Obtener tasas de conversión y comisiones"""
    # Ejemplo de conversión con 5 créditos
    example_credits = 5
    gross = int(example_credits * CREDIT_TO_CASH_RATE)
    fee = int(gross * (WITHDRAWAL_FEE_PERCENT / 100))
    net = gross - fee
    
    example = ConversionExample(
        credits=example_credits,
        gross_amount=gross,
        fee_amount=fee,
        net_amount=net,
        effective_rate_per_credit=net / example_credits if example_credits > 0 else 0
    )
    
    return ConversionRatesRead(
        credit_to_cash_rate=CREDIT_TO_CASH_RATE,
        withdrawal_fee_percent=WITHDRAWAL_FEE_PERCENT,
        example_conversion=example,
        minimum_withdrawal=MIN_WITHDRAWAL_AMOUNT,
        maximum_withdrawal=MAX_WITHDRAWAL_AMOUNT,
        processing_time_hours=WITHDRAWAL_PROCESSING_HOURS
    )


@router.get("/plans", response_model=List[PlanDetailRead])
def get_available_plans():
    """Obtener detalles de todos los planes disponibles"""
    plans_data = get_all_plans_details()
    
    plans = []
    for plan_data in plans_data:
        plans.append(PlanDetailRead(
            name=plan_data["name"],
            credits=plan_data["credits"],
            base_price=plan_data["base_price"],
            discount_percent=plan_data["discount_percent"],
            final_price=plan_data["final_price"],
            prize_contribution_total=plan_data["prize_contribution_total"],
            profit_total=plan_data["profit_total"],
            effective_price_per_credit=plan_data["effective_price_per_credit"],
            discount_amount=plan_data["discount_amount"],
            savings_percentage=plan_data["savings_percentage"]
        ))
    
    return plans


@router.get("/plans/compare", response_model=PlansComparisonResponse)
def compare_plans():
    """Comparar todos los planes disponibles"""
    plans_data = get_all_plans_details()
    
    plan_comparisons = []
    for plan_data in plans_data:
        # Calcular ahorro vs recargarr créditos individualmente
        individual_cost = plan_data["credits"] * CREDIT_PRICE_COP
        savings = individual_cost - plan_data["final_price"]
        
        plan_comparisons.append(PlanComparison(
            plan_name=plan_data["name"],
            credits=plan_data["credits"],
            final_price=plan_data["final_price"],
            price_per_credit=plan_data["effective_price_per_credit"],
            discount_vs_individual=(savings / individual_cost) * 100 if individual_cost > 0 else 0,
            savings_amount=savings,
            recommended_for=plan_data.get("recommended_for", [])
        ))
    
    # Encontrar mejor valor (menor precio por crédito)
    best_value = min(plan_comparisons, key=lambda x: x.price_per_credit)
    cheapest = min(plan_comparisons, key=lambda x: x.final_price)
    
    return PlansComparisonResponse(
        individual_price_per_credit=CREDIT_PRICE_COP,
        plans=plan_comparisons,
        best_value_plan=best_value.plan_name,
        cheapest_plan_per_credit=cheapest.plan_name
    )


@router.post("/calculate-profit", response_model=ProfitCalculationResponse)
def calculate_profit(
    request: ProfitCalculationRequest,
    session: Session = Depends(get_db)
):
    """
    Calcular ganancias para la casa según número de pronósticos
    """
    if request.num_bets < 0:
        raise HTTPException(status_code=400, detail="El número de pronósticos debe ser positivo")
    
    # Cálculos básicos
    total_revenue = request.num_bets * CREDIT_PRICE_COP
    total_prize_contribution = request.num_bets * PRIZE_CONTRIBUTION_PER_CREDIT
    total_profit = request.num_bets * PROFIT_PER_CREDIT
    
    # Calcular impuestos si se solicitan
    tax_amount = 0
    net_profit = total_profit
    
    if request.include_taxes:
        tax_amount = int(total_profit * (request.tax_percentage / 100))
        net_profit = total_profit - tax_amount
    
    return ProfitCalculationResponse(
        num_bets=request.num_bets,
        total_revenue_cop=total_revenue,
        total_prize_pool_contribution=total_prize_contribution,
        total_profit_cop=total_profit,
        profit_percentage=(PROFIT_PER_CREDIT / CREDIT_PRICE_COP) * 100,
        prize_pool_percentage=(PRIZE_CONTRIBUTION_PER_CREDIT / CREDIT_PRICE_COP) * 100,
        tax_amount=tax_amount,
        net_profit_after_taxes=net_profit
    )


@router.get("/financial-summary", response_model=FinancialSummary)
def get_financial_summary(
    days: int = 30,  # Últimos N días
    session: Session = Depends(get_db)
):
    """
    Obtener resumen financiero del sistema
    """
    # Calcular fecha de inicio
    start_date = datetime.now() - timedelta(days=days)
    
    # Transacciones de recarga de créditos
    revenue_transactions = session.query(Transaction).filter(
        Transaction.transaction_type == TransactionType.CREDIT_PURCHASE,
        Transaction.created_at >= start_date,
        Transaction.status == "completed"
    ).all()
    
    # Transacciones de premios
    prize_transactions = session.query(Transaction).filter(
        Transaction.transaction_type == TransactionType.PRIZE_WIN,
        Transaction.created_at >= start_date,
        Transaction.status == "completed"
    ).all()
    
    # Pronósticos
    bets = session.query(Bet).filter(
        Bet.submitted_at >= start_date
    ).all()
    
    # Usuarios activos (que apostaron)
    active_user_ids = list(set([bet.user_id for bet in bets]))
    active_users_count = len(active_user_ids)
    
    # Calcular totales
    total_credits_sold = sum(t.amount_credits for t in revenue_transactions)
    total_revenue = sum(t.amount_cop for t in revenue_transactions)
    total_prizes_paid = sum(t.amount_cop for t in prize_transactions)
    total_profit = total_revenue - total_prizes_paid
    
    # Calcular promedios
    avg_bet_size = 1.0  # Siempre 1 crédito por pronóstico
    profit_margin = (total_profit / total_revenue) * 100 if total_revenue > 0 else 0
    
    # Calcular tasa de conversión (créditos convertidos a efectivo)
    conversion_transactions = session.query(Transaction).filter(
        Transaction.transaction_type == TransactionType.CREDIT_CONVERSION,
        Transaction.created_at >= start_date,
        Transaction.status == "completed"
    ).all()
    
    total_converted_credits = sum(t.amount_credits for t in conversion_transactions)
    conversion_rate = (total_converted_credits / total_credits_sold) * 100 if total_credits_sold > 0 else 0
    
    # Calcular gasto promedio por usuario
    avg_spent_per_user = total_revenue / active_users_count if active_users_count > 0 else 0
    
    return FinancialSummary(
        total_credits_sold=total_credits_sold,
        total_revenue_cop=total_revenue,
        total_prizes_paid_cop=total_prizes_paid,
        total_profit_cop=total_profit,
        average_bet_size=avg_bet_size,
        profit_margin_percentage=profit_margin,
        conversion_rate_percentage=conversion_rate,
        active_users_count=active_users_count,
        avg_spent_per_user=avg_spent_per_user
    )


@router.get("/configuration", response_model=PriceConfiguration)
def get_full_price_configuration():
    """
    Obtener configuración completa de precios del sistema
    """
    # Obtener información de créditos
    credit_info = get_credit_pricing_info()
    
    # Obtener tasas de conversión
    conversion_rates = get_conversion_rates()
    
    # Obtener planes disponibles
    available_plans = get_available_plans()
    
    # Configuración de impuestos
    tax_config = {
        "apply_taxes": APPLY_TAXES,
        "tax_percentage": TAX_PERCENTAGE,
        "tax_included_in_price": False,
        "tax_description": "IVA Colombiano"
    }
    
    return PriceConfiguration(
        credit_pricing=credit_info,
        conversion_rates=conversion_rates,
        available_plans=available_plans,
        last_updated=datetime.now().isoformat(),
        currency="COP",
        tax_configuration=tax_config
    )


@router.get("/best-plan/{usage_pattern}")
def recommend_best_plan(usage_pattern: str):
    """
    Recomendar el mejor plan según patrón de uso
    
    Parámetros:
    - casual: 1-2 pronósticos por semana
    - regular: 3-5 pronósticos por semana  
    - frequent: 6+ pronósticos por semana
    - monthly: Pronósticos todo el mes
    """
    recommendations = {
        "casual": {
            "recommended_plan": "Básico",
            "reason": "Ideal para probar el sistema sin compromiso",
            "monthly_cost": 5000,
            "estimated_savings": 0
        },
        "regular": {
            "recommended_plan": "Plus", 
            "reason": "Ahorras 2% y tienes créditos para varias semanas",
            "monthly_cost": 10000,
            "estimated_savings": 500
        },
        "frequent": {
            "recommended_plan": "Gold",
            "reason": "Máximo ahorro con 3% de descuento para jugadores activos",
            "monthly_cost": 20000,
            "estimated_savings": 1500
        },
        "monthly": {
            "recommended_plan": "Gold",
            "reason": "Mejor valor por crédito para uso constante",
            "monthly_cost": 48500,
            "estimated_savings": 1500
        }
    }
    
    if usage_pattern not in recommendations:
        raise HTTPException(
            status_code=400, 
            detail=f"Patrón de uso inválido. Opciones: {list(recommendations.keys())}"
        )
    
    return recommendations[usage_pattern]