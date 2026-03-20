# backend/app/models/bet/transaction.py
from sqlalchemy import Column, Integer, String, DateTime, Enum, ForeignKey
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db import Base
import enum

class TransactionType(str, enum.Enum):
    """Tipos de transacción"""
    CREDIT_PURCHASE = "credit_purchase"      # Recarga de créditos
    BET_PLACEMENT = "bet_placement"          # Pronósticos realizados
    PRIZE_WIN = "prize_win"                  # Ganancia de premio
    CREDIT_CONVERSION = "credit_conversion"  # Conversión de créditos a dinero
    REFUND = "refund"                        # Reembolso
    ADMIN_ADJUSTMENT = "admin_adjustment"    # Ajuste administrativo

class TransactionStatus(str, enum.Enum):
    """Estados de transacción"""
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"

class Transaction(Base):
    __tablename__ = "transactions"
    
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    wallet_id = Column(Integer, ForeignKey("user_wallets.id"), nullable=False)
    
    # Información de la transacción
    transaction_type = Column(Enum(TransactionType), nullable=False)
    status = Column(Enum(TransactionStatus), default=TransactionStatus.PENDING)
    
    # Montos
    amount_cop = Column(Integer, default=0)          # Dinero en COP
    amount_credits = Column(Integer, default=0)      # Créditos
    fee_cop = Column(Integer, default=0)             # Comisión
    net_amount_cop = Column(Integer, default=0)      # Monto neto (amount - fee)
    
    # Referencias
    reference_id = Column(Integer, nullable=True)    # ID de referencia (bet_id, plan_id, etc.)
    reference_type = Column(String(50), nullable=True)  # Tipo de referencia
    
    # Metadatos
    description = Column(String(500), nullable=True)
    payment_method = Column(String(50), nullable=True)  # credit_card, pse, etc.
    payment_reference = Column(String(100), nullable=True)  # Ref de pago externo
    
    # Auditoría
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    completed_at = Column(DateTime, nullable=True)
    
    # Relaciones
    user = relationship("User", back_populates="transactions")
    wallet = relationship("UserWallet", back_populates="transactions")
    
    def __repr__(self):
        return f"<Transaction {self.id} - {self.transaction_type} - {self.status}>"
    
    @property
    def is_successful(self):
        return self.status == TransactionStatus.COMPLETED
    
    def complete(self):
        """Marcar transacción como completada"""
        from datetime import datetime
        self.status = TransactionStatus.COMPLETED
        self.completed_at = datetime.now()