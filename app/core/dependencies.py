# backend/app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from app.core.security import get_current_user
from app.models.user.user import User

def admin_required(user: User = Depends(get_current_user)):
    if user.role.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador"
        )
    return user

# backend/app/core/dependencies.py
from fastapi import Depends, HTTPException, status
from app.core.security import get_current_user
from app.models.user.user import User

def admin_required(user: User = Depends(get_current_user)):
    if user.role.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador"
        )
    return user

# ✅ Agrega esta nueva función
def get_current_admin_user(user: User = Depends(get_current_user)):
    """Obtener usuario actual solo si es admin"""
    if user.role.upper() != "ADMIN":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="No tienes permisos de administrador"
        )
    return user