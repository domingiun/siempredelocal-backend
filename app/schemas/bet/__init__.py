# backend/app/schemas/bet/__init__.py
# Importar schemas de pricing
from .pricing import (
    CreditPricingBase, CreditPricingCreate, CreditPricingRead,
    ConversionRatesBase, ConversionRatesCreate, ConversionRatesRead,
    ConversionExample,
    PlanDetailBase, PlanDetailCreate, PlanDetailRead,
    ProfitCalculationRequest, ProfitCalculationResponse,
    PlansComparisonResponse, PlanComparison,
    FinancialSummary,
    PriceConfiguration
)

# Añadir a __all__ list:
__all__ = [
    # ... otros schemas existentes ...
    
    # Schemas de pricing
    "CreditPricingBase", "CreditPricingCreate", "CreditPricingRead",
    "ConversionRatesBase", "ConversionRatesCreate", "ConversionRatesRead",
    "ConversionExample",
    "PlanDetailBase", "PlanDetailCreate", "PlanDetailRead",
    "ProfitCalculationRequest", "ProfitCalculationResponse",
    "PlansComparisonResponse", "PlanComparison",
    "FinancialSummary",
    "PriceConfiguration",
]