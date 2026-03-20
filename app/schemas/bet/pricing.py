from typing import Dict, Any, List
from pydantic import BaseModel, Field


# ==================== PRECIOS DE CRÉDITOS ====================
class CreditPricingBase(BaseModel):
    """Base para precios de créditos"""
    credit_price_cop: int = Field(description="Precio de 1 crédito en COP")
    prize_contribution_per_credit: int = Field(description="Contribución al premio por crédito")
    profit_per_credit: int = Field(description="Ganancia para la casa por crédito")

class CreditPricingCreate(CreditPricingBase):
    """Para crear configuración de precios"""
    pass

class CreditPricingRead(CreditPricingBase):
    """Para leer información de precios"""
    required_credits_per_bet: int = Field(description="Créditos requeridos por apuesta")
    min_points_to_win: int = Field(description="Puntos mínimos para ganar premio")
    max_predictions_per_bet: int = Field(default=10, description="Máximo de predicciones por apuesta")
    
    class Config:
        from_attributes = True


# ==================== TASAS DE CONVERSIÓN ====================
class ConversionExample(BaseModel):
    """Ejemplo de conversión"""
    credits: int = Field(description="Cantidad de créditos a convertir")
    gross_amount: int = Field(description="Monto bruto antes de comisión")
    fee_amount: int = Field(description="Comisión aplicada")
    net_amount: int = Field(description="Monto neto recibido")
    effective_rate_per_credit: float = Field(description="Tasa efectiva por crédito")

class ConversionRatesBase(BaseModel):
    """Base para tasas de conversión"""
    credit_to_cash_rate: float = Field(description="Tasa de cambio crédito a efectivo")
    withdrawal_fee_percent: float = Field(description="Porcentaje de comisión por retiro")

class ConversionRatesCreate(ConversionRatesBase):
    """Para crear configuración de tasas"""
    pass

class ConversionRatesRead(ConversionRatesBase):
    """Para leer tasas de conversión"""
    example_conversion: ConversionExample
    minimum_withdrawal: int = Field(default=20000, description="Retiro mínimo permitido")
    maximum_withdrawal: int = Field(default=1000000, description="Retiro máximo permitido")
    processing_time_hours: int = Field(default=24, description="Tiempo de procesamiento en horas")
    
    class Config:
        from_attributes = True


# ==================== DETALLES DE PLANES ====================
class PlanDetailBase(BaseModel):
    """Base para detalles de plan"""
    name: str = Field(description="Nombre del plan")
    credits: int = Field(description="Créditos incluidos")
    base_price: int = Field(description="Precio base sin descuento")

class PlanDetailCreate(PlanDetailBase):
    """Para crear detalles de plan"""
    discount_percent: float = Field(description="Porcentaje de descuento")
    prize_contribution: int = Field(description="Contribución al premio por crédito")

class PlanDetailRead(PlanDetailBase):
    """Para leer detalles de plan"""
    discount_percent: float = Field(description="Porcentaje de descuento")
    final_price: int = Field(description="Precio final con descuento")
    prize_contribution_total: int = Field(description="Contribución total al premio")
    profit_total: int = Field(description="Ganancia total para la casa")
    effective_price_per_credit: float = Field(description="Precio efectivo por crédito")
    discount_amount: int = Field(description="Monto descontado")
    savings_percentage: float = Field(description="Porcentaje de ahorro vs recarga individual")
    
    class Config:
        from_attributes = True


# ==================== CÁLCULO DE GANANCIAS ====================
class ProfitCalculationRequest(BaseModel):
    """Request para cálculo de ganancias"""
    num_bets: int = Field(ge=0, description="Número de pronósticos")
    include_taxes: bool = Field(default=False, description="Incluir cálculo de impuestos")
    tax_percentage: float = Field(default=19.0, ge=0, le=100, description="Porcentaje de impuestos")

class ProfitCalculationResponse(BaseModel):
    """Respuesta de cálculo de ganancias"""
    num_bets: int
    total_revenue_cop: int = Field(description="Ingresos totales")
    total_prize_pool_contribution: int = Field(description="Contribución total al pozo de premios")
    total_profit_cop: int = Field(description="Ganancia total para la casa")
    profit_percentage: float = Field(description="Porcentaje de ganancia")
    prize_pool_percentage: float = Field(description="Porcentaje destinado a premios")
    
    # Campos opcionales con impuestos
    tax_amount: int = Field(default=0, description="Monto de impuestos")
    net_profit_after_taxes: int = Field(default=0, description="Ganancia neta después de impuestos")
    
    class Config:
        from_attributes = True


# ==================== COMPARACIÓN DE PLANES ====================
class PlanComparison(BaseModel):
    """Comparación entre planes"""
    plan_name: str
    credits: int
    final_price: int
    price_per_credit: float
    discount_vs_individual: float = Field(description="Descuento vs recargar créditos individualmente")
    savings_amount: int = Field(description="Ahorro en COP vs recargar individualmente")
    recommended_for: List[str] = Field(description="Recomendado para")

class PlansComparisonResponse(BaseModel):
    """Respuesta de comparación de planes"""
    individual_price_per_credit: int
    plans: List[PlanComparison]
    best_value_plan: str = Field(description="Plan con mejor valor")
    cheapest_plan_per_credit: str = Field(description="Plan más económico por crédito")
    
    class Config:
        from_attributes = True


# ==================== RESUMEN FINANCIERO ====================
class FinancialSummary(BaseModel):
    """Resumen financiero del sistema"""
    total_credits_sold: int
    total_revenue_cop: int
    total_prizes_paid_cop: int
    total_profit_cop: int
    average_bet_size: float = Field(description="Pronósticos promedio en créditos")
    profit_margin_percentage: float
    conversion_rate_percentage: float = Field(description="Porcentaje de créditos convertidos a efectivo")
    active_users_count: int
    avg_spent_per_user: float
    
    class Config:
        from_attributes = True


# ==================== CONFIGURACIÓN DE PRECIOS ====================
class PriceConfiguration(BaseModel):
    """Configuración completa de precios"""
    credit_pricing: CreditPricingRead
    conversion_rates: ConversionRatesRead
    available_plans: List[PlanDetailRead]
    last_updated: str = Field(description="Fecha de última actualización")
    currency: str = Field(default="COP", description="Moneda")
    tax_configuration: Dict[str, Any] = Field(
        default={},
        description="Configuración de impuestos"
    )
    
    class Config:
        from_attributes = True