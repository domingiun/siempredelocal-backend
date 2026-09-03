# backend/app/models/constants/bet_constants.py
from typing import Final, Dict, Any, List
from datetime import datetime

# ==================== PRECIOS Y CONTRIBUCIONES ====================
CREDIT_PRICE_COP: Final[int] = 5000  # Precio de 1 crédito
PRIZE_CONTRIBUTION_PER_CREDIT: Final[int] = 1950  # Lo que va al premio por crédito
PROFIT_PER_CREDIT: Final[int] = CREDIT_PRICE_COP - PRIZE_CONTRIBUTION_PER_CREDIT  # $880 ganancia

# ==================== REGLAS DE APUESTAS ====================
REQUIRED_CREDITS_PER_BET: Final[int] = 1  # 1 crédito por pronóstico
MIN_POINTS_TO_WIN: Final[int] = 8  # Puntos mínimos para ganar (sobre 12 posibles)
MAX_PREDICTIONS_PER_BET: Final[int] = 12  # 12 partidos por fecha
MIN_BETDATE_MATCHES: Final[int] = 12  # Mínimo de partidos por fecha
MAX_BETDATE_MATCHES: Final[int] = 12  # Máximo de partidos por fecha

# ==================== CONVERSIÓN DE CRÉDITOS ====================
CREDIT_TO_CASH_RATE: Final[float] = 4500.0  # 1 crédito = $4,500 COP
WITHDRAWAL_FEE_PERCENT: Final[float] = 5.0  # 5% comisión por retiro
MIN_WITHDRAWAL_AMOUNT: Final[int] = 20000  # Retiro mínimo: $20,000 COP
MAX_WITHDRAWAL_AMOUNT: Final[int] = 1000000  # Retiro máximo: $1,000,000 COP
WITHDRAWAL_PROCESSING_HOURS: Final[int] = 24  # Tiempo de procesamiento

# ==================== CONFIGURACIÓN DE PLANES ====================
PLANS_CONFIG: Final[Dict[str, Dict[str, Any]]] = {
    "basic": {
        "name": "Básico",
        "credits": 1,
        "base_price": 5000,
        "discount_percent": 0.0,
        "prize_contribution": 1950,
        "description": "Perfecto para probar el sistema",
        "features": ["1 crédito", "1 apuesta", "Sin descuento"],
        "recommended_for": ["Nuevos usuarios", "Prueba única"]
    },
    "plus": {
        "name": "Plus",
        "credits": 5,
        "base_price": 25000,  # 5 * 5000
        "discount_percent": 2.0,
        "prize_contribution": 1950,
        "description": "Ahorra 2% recargando 5 créditos",
        "features": ["5 créditos", "5 pronósticos", "2% descuento", "Ahorro: $500"],
        "recommended_for": ["Jugadores ocasionales", "Fines de semana"]
    },
    "gold": {
        "name": "Gold",
        "credits": 10,
        "base_price": 50000,  # 10 * 5000
        "discount_percent": 3.0,
        "prize_contribution": 1950,
        "description": "Máximo ahorro con 3% de descuento",
        "features": ["10 créditos", "10 pronósticos", "3% descuento", "Ahorro: $1,500", "Mejor valor"],
        "recommended_for": ["Jugadores frecuentes", "Todo el mes"]
    }
}

# ==================== IMPUESTOS ====================
TAX_PERCENTAGE: Final[float] = 19.0  # IVA colombiano
APPLY_TAXES: Final[bool] = False  # Si se aplican impuestos (configurable)

# ==================== FECHAS Y TIEMPOS ====================
BET_CLOSE_BEFORE_MATCH_HOURS: Final[int] = 1  # Cierre pronósticos 1 hora antes del partido
MIN_BETDATE_DURATION_DAYS: Final[int] = 1  # Mínimo duración de fecha
MAX_BETDATE_DURATION_DAYS: Final[int] = 7  # Máximo duración de fecha
PRIZE_CLAIM_DEADLINE_DAYS: Final[int] = 30  # Días para reclamar premio

# ==================== LÍMITES DEL SISTEMA ====================
MAX_BETS_PER_USER_PER_DATE: Final[int] = 1  # Máximo 1 pronóstico por usuario por fecha
MAX_ACTIVE_BETDATES: Final[int] = 5  # Máximo de fechas activas simultáneas
MIN_AGE_FOR_BETTING: Final[int] = 18  # Edad mínima para apostar
MAX_CREDITS_PER_USER: Final[int] = 1000  # Máximo créditos por usuario

# ==================== CÁLCULOS PREDEFINIDOS ====================
def calculate_plan_details(plan_key: str) -> Dict[str, Any]:
    """Calcular detalles completos de un plan"""
    if plan_key not in PLANS_CONFIG:
        raise ValueError(f"Plan {plan_key} no encontrado")
    
    config = PLANS_CONFIG[plan_key]
    base_price = config["base_price"]
    discount_amount = base_price * (config["discount_percent"] / 100)
    final_price = int(base_price - discount_amount)
    
    return {
        "name": config["name"],
        "credits": config["credits"],
        "base_price": base_price,
        "discount_percent": config["discount_percent"],
        "discount_amount": int(discount_amount),
        "final_price": final_price,
        "prize_contribution_total": config["prize_contribution"] * config["credits"],
        "profit_total": (CREDIT_PRICE_COP - config["prize_contribution"]) * config["credits"],
        "effective_price_per_credit": final_price / config["credits"],
        "savings_vs_individual": base_price - final_price,
        "savings_percentage": (discount_amount / base_price) * 100 if base_price > 0 else 0,
        "description": config.get("description", ""),
        "features": config.get("features", []),
        "recommended_for": config.get("recommended_for", [])
    }

def get_all_plans_details() -> List[Dict[str, Any]]:
    """Obtener detalles de todos los planes"""
    return [calculate_plan_details(plan_key) for plan_key in PLANS_CONFIG.keys()]

def get_best_value_plan() -> Dict[str, Any]:
    """Obtener el plan con mejor valor (menor precio por crédito)"""
    plans = get_all_plans_details()
    return min(plans, key=lambda x: x["effective_price_per_credit"])

# ==================== VERSIÓN Y METADATOS ====================
CONFIG_VERSION: Final[str] = "1.0.0"
LAST_UPDATED: Final[str] = "2024-01-01"
CURRENCY: Final[str] = "COP"