# backend/app/models/bet/audit_log.py
"""
M7: Tabla de auditoría inmutable para operaciones administrativas.
Los registros NUNCA se borran ni modifican — solo INSERT.
Almacena quién hizo qué, cuándo, y sobre qué recurso.
"""
from sqlalchemy import Column, Integer, String, DateTime, Text, ForeignKey
from sqlalchemy.sql import func
from app.db import Base


class AuditLog(Base):
    __tablename__ = "audit_logs"

    id = Column(Integer, primary_key=True, index=True)

    # Quién realizó la acción
    admin_user_id = Column(Integer, ForeignKey("users.id"), nullable=False, index=True)
    admin_username = Column(String(100), nullable=False)  # Snapshot del username al momento

    # Qué acción se realizó
    action = Column(String(100), nullable=False, index=True)
    # Ejemplos: "approve_credit_purchase", "reject_withdraw", "add_credits", "finalize_betdate"

    # Sobre qué recurso
    resource_type = Column(String(50), nullable=False)
    # Ejemplos: "transaction", "betdate", "user_wallet"
    resource_id = Column(Integer, nullable=True)

    # Detalles adicionales (JSON string)
    details = Column(Text, nullable=True)
    # Ejemplo: '{"credits_added": 50, "user_id": 12, "reason": "compensación"}'

    # Cuándo — inmutable, establecido por el servidor
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
