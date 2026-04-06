# backend/app/core/security.py
from datetime import datetime, timedelta
from jose import JWTError, jwt
from fastapi import Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session
from typing import Optional
import bcrypt

from app.db import get_db
from app.models.user.user import User
from app.config import settings

# Se mantiene para compatibilidad con Swagger UI y clientes API directos
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="auth/login", auto_error=False)

def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verificar contraseña usando bcrypt directamente"""
    try:
        # bcrypt espera que el hash esté en bytes
        if hashed_password.startswith("$2b$"):
            # Es un hash bcrypt válido
            return bcrypt.checkpw(
                plain_password.encode('utf-8'), 
                hashed_password.encode('utf-8')
            )
        else:
            # Manejar hashes antiguos (migración)
            return legacy_verify_password(plain_password, hashed_password)
    except Exception:
        return False

def get_password_hash(password: str) -> str:
    """Obtener hash de contraseña usando bcrypt directamente"""
    # Limitar longitud a 72 bytes como recomienda bcrypt
    if len(password) > 72:
        password = password[:72]
    
    # Generar salt y hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password.encode('utf-8'), salt)
    
    # Devolver como string
    return hashed.decode('utf-8')

def legacy_verify_password(plain_password: str, hashed_password: str) -> bool:
    """Para verificar hashes antiguos si los hay"""
    # Si tienes hashes antiguos, aquí los manejas
    # Por ahora, solo retornamos False
    return False

def create_access_token(data: dict, expires_delta: timedelta | None = None):
    """Crear token JWT"""
    to_encode = data.copy()
    
    if expires_delta:
        expire = datetime.utcnow() + expires_delta
    else:
        expire = datetime.utcnow() + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    
    to_encode.update({"exp": expire})
    
    # ✅ Asegurar que los datos del usuario estén incluidos
    if "sub" not in to_encode:
        raise ValueError("El campo 'sub' (subject) es requerido para JWT")
    
    encoded_jwt = jwt.encode(
        to_encode, 
        settings.SECRET_KEY, 
        algorithm=settings.ALGORITHM
    )
    return encoded_jwt

def _decode_token(token: str, credentials_exception: HTTPException) -> str:
    """Decodifica y valida un JWT, devuelve el username."""
    try:
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        username: str = payload.get("sub")
        if username is None:
            raise credentials_exception
        return username
    except JWTError:
        raise credentials_exception


def get_current_user(
    request: Request,
    bearer_token: Optional[str] = Depends(oauth2_scheme),
    db: Session = Depends(get_db),
) -> User:
    """
    Obtener usuario actual desde JWT.
    Prioridad: httpOnly cookie → Authorization Bearer header.
    Esto permite al frontend usar cookies seguras mientras Swagger/apps
    siguen funcionando con el header.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="No se pudieron validar las credenciales",
        headers={"WWW-Authenticate": "Bearer"},
    )

    # 1. Intentar cookie httpOnly (más seguro contra XSS)
    token: Optional[str] = request.cookies.get("access_token")

    # 2. Fallback a Authorization: Bearer (Swagger, apps móviles, API clients)
    if not token:
        token = bearer_token

    if not token:
        raise credentials_exception

    username = _decode_token(token, credentials_exception)

    user = db.query(User).filter(User.username == username).first()
    if user is None:
        raise credentials_exception

    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )

    return user