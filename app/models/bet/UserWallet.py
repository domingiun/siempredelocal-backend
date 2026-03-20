# backend/app/models/bet/UserWallet.py
from sqlalchemy import Column, Integer, ForeignKey
from sqlalchemy.orm import relationship
from app.db import Base

class UserWallet(Base):
    __tablename__ = "user_wallets"

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    
    # Saldo y créditos actuales
    credits = Column(Integer, default=0)
    balance_cop = Column(Integer, default=0)

    # Registro opcional de totales
    total_credits_purchased = Column(Integer, default=0)  
    total_prizes_won = Column(Integer, default=0) 

    # Relaciones
    user = relationship("User", back_populates="wallet")
    transactions = relationship(
        "Transaction",
        back_populates="wallet",
        cascade="all, delete-orphan"
    )
