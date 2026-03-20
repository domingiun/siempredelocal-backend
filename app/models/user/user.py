# backend/app/models/user/user.py
from sqlalchemy import Column, Integer, String, Boolean, DateTime, Enum as SQLEnum
from sqlalchemy.sql import func
from sqlalchemy.orm import relationship
from app.db import Base
import enum

class UserRole(str, enum.Enum):
    """Roles de usuario"""
    ADMIN = "admin"
    USER = "user"

class User(Base):
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True, index=True)
    
    # Información básica
    username = Column(String(50), unique=True, index=True, nullable=False)
    email = Column(String(100), unique=True, index=True, nullable=False)
    full_name = Column(String(100), nullable=True)
    phone = Column(String(20), nullable=True)
    avatar_url = Column(String(255), nullable=True)
    
    # Seguridad
    hashed_password = Column(String(255), nullable=False)
    
    # Estado y permisos
    is_active = Column(Boolean, default=True)
    role = Column(SQLEnum(UserRole), default=UserRole.USER, nullable=False)
    
    # Campos legacy para compatibilidad (opcional)
    is_admin = Column(Boolean, default=False)  # Mantener para compatibilidad
    
    # Auditoría
    created_at = Column(DateTime, server_default=func.now())
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now())
    
    def __repr__(self):
        return f"<User {self.username} ({self.role})>"
    
    wallet = relationship("UserWallet", back_populates="user", uselist=False)
    bets = relationship("Bet", back_populates="user")
    transactions = relationship("Transaction", back_populates="user", cascade="all, delete-orphan")
    reset_tokens = relationship("PasswordResetToken", back_populates="user", cascade="all, delete-orphan")

    @property
    def is_admin_property(self):
        """Propiedad para mantener compatibilidad con código que usa is_admin"""
        return self.role == UserRole.ADMIN
    
