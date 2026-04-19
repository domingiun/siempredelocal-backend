# backend/app/schemas/user/user.py
from pydantic import BaseModel, EmailStr, Field, validator
from typing import Optional, List
from enum import Enum
from datetime import datetime

class UserRole(str, Enum):
    ADMIN = "admin"
    USER = "user"

class UserBase(BaseModel):
    email: EmailStr
    username: str = Field(..., min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=20)
    
    @validator('username')
    def username_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('El username no puede estar vacío')
        return v
    
    @validator('username')
    def username_alphanumeric(cls, v):
        # Permitir solo letras, números y guiones bajos
        import re
        if not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('El username solo puede contener letras, números y guiones bajos')
        return v
    
    @validator('email')
    def email_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('El email no puede estar vacío')
        return v

    @validator('phone')
    def phone_valid(cls, v):
        if v is None:
            return v
        if v.strip() == "":
            raise ValueError('El celular no puede estar vacio')
        import re
        if not re.match(r'^[0-9+()\\-\\s]+$', v):
            raise ValueError('El celular solo puede contener numeros, espacios y +()-')
        return v

# ========== NUEVOS ESQUEMAS PARA PERFIL ==========

class ProfileUpdate(BaseModel):
    """
    Esquema para actualizar perfil (usuario normal)
    - No incluye role ni is_active
    """
    email: Optional[EmailStr] = None
    username: Optional[str] = Field(None, min_length=3, max_length=50)
    full_name: Optional[str] = Field(None, max_length=100)
    phone: Optional[str] = Field(None, min_length=7, max_length=20)
    password: Optional[str] = Field(None, min_length=6, max_length=72)
    
    @validator('username')
    def username_not_empty_optional(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError('El username no puede estar vacío')
        return v
    
    @validator('username')
    def username_alphanumeric_optional(cls, v):
        import re
        if v and not re.match(r'^[a-zA-Z0-9_]+$', v):
            raise ValueError('El username solo puede contener letras, números y guiones bajos')
        return v
    
    @validator('email')
    def email_not_empty_optional(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError('El email no puede estar vacío')
        return v
    
    @validator('phone')
    def phone_valid_optional(cls, v):
        if v is None:
            return v
        if v.strip() == "":
            raise ValueError('El celular no puede estar vacio')
        import re
        if not re.match(r'^[0-9+()\\-\\s]+$', v):
            raise ValueError('El celular solo puede contener numeros, espacios y +()-')
        return v

    @validator('password')
    def password_not_empty(cls, v):
        if v is not None and v.strip() == "":
            raise ValueError('La contraseña no puede estar vacía')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "usuario@ejemplo.com",
                "username": "usuario123",
                "full_name": "Usuario Ejemplo",
                "password": "NuevaContraseña123"
            }
        }

class UserUpdate(ProfileUpdate):
    """
    Esquema para actualizar usuario (admin)
    - Extiende ProfileUpdate y añade campos de admin
    """
    role: Optional[str] = Field(None, pattern="^(admin|user)$")
    is_active: Optional[bool] = None
    
    @validator('role')
    def validate_role(cls, v):
        if v and v not in ["admin", "user"]:
            raise ValueError('Rol debe ser "admin" o "user"')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "admin@ejemplo.com",
                "username": "admin_user",
                "full_name": "Administrador",
                "password": "NuevaContraseña456",
                "role": "admin",
                "is_active": True
            }
        }

# ========== ESQUEMAS EXISTENTES (CON ALGUNOS AJUSTES) ==========

class UserCreate(UserBase):
    phone: str = Field(..., min_length=7, max_length=20)
    password: str = Field(..., min_length=6)
    
    @validator('password')
    def password_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('La contraseña no puede estar vacía')
        
        # Limit to 72 chars for bcrypt (silently truncated by bcrypt anyway)
        if len(v) > 72:
            pass
        
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "email": "usuario@ejemplo.com",
                "username": "usuario123",
                "full_name": "Usuario Ejemplo",
                "password": "Contraseña123!"
            }
        }

class UserLogin(BaseModel):
    username: str
    password: str
    
    @validator('username')
    def username_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('El username no puede estar vacío')
        return v
    
    @validator('password')
    def password_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('La contraseña no puede estar vacía')
        return v

class UserResponse(UserBase):
    id: int
    is_active: bool
    role: UserRole
    avatar_url: Optional[str] = None
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True
        json_schema_extra = {
            "example": {
                "id": 1,
                "email": "admin@siempredelocal.com",
                "username": "admin",
                "full_name": "Administrador Principal",
                "is_active": True,
                "role": "admin",
                "created_at": "2024-01-09T22:13:34.631Z",
                "updated_at": "2024-01-09T22:13:34.631Z"
            }
        }

class UserResponseList(BaseModel):
    """
    Esquema para listar usuarios con información adicional
    """
    users: List[UserResponse]
    total: int
    page: int
    per_page: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "users": [
                    {
                        "id": 1,
                        "email": "admin@siempredelocal.com",
                        "username": "admin",
                        "full_name": "Administrador Principal",
                        "is_active": True,
                        "role": "admin"
                    }
                ],
                "total": 1,
                "page": 1,
                "per_page": 10
            }
        }

class Token(BaseModel):
    access_token: str
    token_type: str
    user: Optional[UserResponse] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "access_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
                "token_type": "bearer",
                "user": {
                    "id": 1,
                    "email": "admin@siempredelocal.com",
                    "username": "admin",
                    "full_name": "Administrador Principal",
                    "is_active": True,
                    "role": "admin"
                }
            }
        }

class TokenData(BaseModel):
    username: Optional[str] = None
    role: Optional[str] = None
    user_id: Optional[int] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "username": "admin",
                "role": "admin",
                "user_id": 1
            }
        }

class PasswordChange(BaseModel):
    """
    Esquema específico para cambio de contraseña
    """
    current_password: str = Field(..., min_length=6, max_length=72)
    new_password: str = Field(..., min_length=6, max_length=72)
    
    @validator('current_password', 'new_password')
    def password_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('La contraseña no puede estar vacía')
        return v
    
    @validator('new_password')
    def passwords_not_same(cls, v, values):
        if 'current_password' in values and v == values['current_password']:
            raise ValueError('La nueva contraseña debe ser diferente a la actual')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "current_password": "ContraseñaActual123",
                "new_password": "NuevaContraseña456"
            }
        }

class UserRoleUpdate(BaseModel):
    role: UserRole
    
    class Config:
        json_schema_extra = {
            "example": {
                "role": "admin"
            }
        }

class UserStatusUpdate(BaseModel):
    is_active: bool
    
    class Config:
        json_schema_extra = {
            "example": {
                "is_active": True
            }
        }

class UserSearchQuery(BaseModel):
    search: Optional[str] = None
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    page: int = Field(1, ge=1)
    per_page: int = Field(10, ge=1, le=100)
    
    class Config:
        json_schema_extra = {
            "example": {
                "search": "admin",
                "role": "admin",
                "is_active": True,
                "page": 1,
                "per_page": 10
            }
        }

class UserStats(BaseModel):
    total_users: int
    active_users: int
    admin_users: int
    regular_users: int
    inactive_users: int
    
    class Config:
        json_schema_extra = {
            "example": {
                "total_users": 10,
                "active_users": 8,
                "admin_users": 2,
                "regular_users": 6,
                "inactive_users": 2
            }
        }

class MessageResponse(BaseModel):
    message: str
    user_id: Optional[int] = None
    details: Optional[dict] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "message": "Usuario actualizado exitosamente",
                "user_id": 1,
                "details": {"fields_updated": ["email", "full_name"]}
            }
        }

class BulkUserUpdate(BaseModel):
    user_ids: List[int]
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    
    @validator('user_ids')
    def user_ids_not_empty(cls, v):
        if not v:
            raise ValueError('La lista de IDs de usuarios no puede estar vacía')
        return v
    
    class Config:
        json_schema_extra = {
            "example": {
                "user_ids": [1, 2, 3],
                "role": "admin",
                "is_active": True
            }
        }

# ========== ESQUEMA PARA ACTUALIZACIÓN RÁPIDA DE USUARIO ==========

class UserQuickUpdate(BaseModel):
    """
    Esquema para actualización rápida (usado en listas/tablas)
    """
    full_name: Optional[str] = Field(None, max_length=100)
    role: Optional[UserRole] = None
    is_active: Optional[bool] = None
    
    class Config:
        json_schema_extra = {
            "example": {
                "full_name": "Nuevo Nombre",
                "role": "admin",
                "is_active": True
            }
        }


# ========== RECUPERACION DE CONTRASENA ==========

class PasswordResetRequest(BaseModel):
    channel: str = Field(..., pattern="^(email|whatsapp)$")
    email: Optional[EmailStr] = None
    phone: Optional[str] = Field(None, min_length=7, max_length=20)

    @validator('email')
    def email_required_for_channel(cls, v, values):
        if values.get('channel') == 'email' and not v:
            raise ValueError('Email requerido')
        return v

    @validator('phone')
    def phone_required_for_channel(cls, v, values):
        if values.get('channel') == 'whatsapp' and not v:
            raise ValueError('Celular requerido')
        if v is None:
            return v
        if v.strip() == "":
            raise ValueError('El celular no puede estar vacio')
        import re
        if not re.match(r'^[0-9+()\-\s]+$', v):
            raise ValueError('El celular solo puede contener numeros, espacios y +()-')
        return v

class PasswordResetConfirm(BaseModel):
    token: str = Field(..., min_length=20)
    new_password: str = Field(..., min_length=6, max_length=72)

    @validator('new_password')
    def password_not_empty(cls, v):
        if v.strip() == "":
            raise ValueError('La contrasena no puede estar vacia')
        return v
