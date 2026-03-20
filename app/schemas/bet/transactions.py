# backend/app/schemas/bet/transactions.py
from datetime import datetime
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field, validator
from enum import Enum


class PaymentMethod(str, Enum):
    NEQUI = "nequi"
    ADMIN = "admin"

class PurchaseCreditsRequest(BaseModel):
    plan_id: int
    payment_method: PaymentMethod = PaymentMethod.NEQUI
    payment_reference: Optional[str] = Field(
         default=None,
         description="Referencia o comprobante enviado por WhatsApp"
    )

class PurchaseCreditsResponse(BaseModel):
    success: bool
    message: str
    transaction_id: int
    credits_added: int
    total_paid: int
    prize_contribution: int
    new_balance: int
    timestamp: datetime

class ConvertCreditsRequest(BaseModel):
    credits_to_convert: int = Field(
        gt=0,
        le=1000,
        description="Cantidad de créditos a convertir"
    )

class PointsToCreditsRequest(BaseModel):
    points_to_convert: int = Field(
        gt=0,
        description="Cantidad de puntos a convertir a créditos"
    )
    credit_value_pts: int = Field(
        default=5000,
        description="Valor en PTS por crédito"
    )

class WithdrawPointsRequest(BaseModel):
    amount_pts: int = Field(
        gt=0,
        description="Monto de puntos a retirar"
    )
    payment_method: PaymentMethod = PaymentMethod.NEQUI

class ConvertCreditsResponse(BaseModel):
    success: bool
    message: str
    transaction_id: int
    credits_converted: int
    amount_received: int
    fee: int
    new_credits_balance: int
    new_cash_balance: int
    timestamp: datetime

class TransactionDetail(BaseModel):
    id: int
    transaction_type: str
    status: str
    amount_cop: int
    amount_credits: int
    fee_cop: int
    net_amount_cop: int
    description: Optional[str]
    reference_id: Optional[int]
    reference_type: Optional[str]
    created_at: datetime
    completed_at: Optional[datetime]
    
    # ✅ CAMPOS NUEVOS PARA COMPATIBILIDAD CON FRONTEND
    amount: int = Field(default=0, description="Monto principal (para frontend)")
    currency: str = Field(default="COP", description="Moneda")
    credits_affected: int = Field(default=0, description="Créditos afectados (para frontend)")
    
    # Validación para calcular campos derivados
    @validator('amount', pre=True, always=True)
    def calculate_amount(cls, v, values):
        """Calcular amount basado en transaction_type"""
        if v != 0:  # Si ya viene con valor, usarlo
            return v
        
        transaction_type = values.get('transaction_type', '')
        
        # Lógica de cálculo según tipo
        if transaction_type == "CREDIT_PURCHASE":
            return values.get('amount_cop', 0)  # Es negativo (gasto)
        elif transaction_type == "PRIZE_WIN":
            return values.get('net_amount_cop', 0)  # Es positivo (ganancia)
        elif transaction_type == "BET_PLACEMENT":
            return -5000  # Fijo: -$5,000 COP por apuesta
        elif transaction_type == "CREDIT_CONVERSION":
            return values.get('net_amount_cop', 0)  # Retiro positivo
        else:
            return values.get('amount_cop', 0)
    
    @validator('credits_affected', pre=True, always=True)
    def calculate_credits_affected(cls, v, values):
        """Calcular créditos afectados"""
        if v != 0:  # Si ya viene con valor, usarlo
            return v
        
        transaction_type = values.get('transaction_type', '')
        
        if transaction_type == "CREDIT_PURCHASE":
            return values.get('amount_credits', 0)  # Créditos recargados
        elif transaction_type == "BET_PLACEMENT":
            return -1  # Siempre -1 crédito por pronóstico
        elif transaction_type == "CREDIT_CONVERSION":
            return -values.get('amount_credits', 0)  # Créditos convertidos
        else:
            return 0


class TransactionHistoryResponse(BaseModel):
    user_id: int
    total_transactions: int
    total_spent: int
    total_earned: int
    current_credits: int
    current_balance_cop: int
    transactions: List[TransactionDetail]

class WalletSummary(BaseModel):
    user_id: int
    credits: int
    balance_cop: int
    total_credits_purchased: int
    total_prizes_won: int
    active_bets: int
    can_withdraw: bool = Field(description="Si tiene saldo suficiente para retirar")
    withdrawal_fee_percent: float = Field(default=5.0, description="Porcentaje de comisión por retiro")
    
    @property
    def available_for_withdrawal(self) -> int:
        """Dinero disponible para retiro después de comisión"""
        if self.balance_cop <= 0:
            return 0
        fee = int(self.balance_cop * (self.withdrawal_fee_percent / 100))
        return self.balance_cop - fee
