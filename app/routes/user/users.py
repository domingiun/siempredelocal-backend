# backend/app/routes/user/users.py
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session
from typing import List, Dict, Any

from app.db import get_db
from app.models.user.user import User
from app.schemas.user.user import UserResponse, UserUpdate, ProfileUpdate
from app.core.security import get_password_hash, get_current_user, verify_password
from app.core.dependencies import admin_required

router = APIRouter(prefix="/users", tags=["users"])

# -----------------------------
# GET USERS (todos)
# -----------------------------
@router.get("/", response_model=List[UserResponse])
def get_users(db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Obtener todos los usuarios activos (cualquier usuario autenticado)
    """
    users = db.query(User).filter(User.is_active == True).all()
    return users

# -----------------------------
# GET USER BY ID
# -----------------------------
@router.get("/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db), current_user: User = Depends(get_current_user)):
    """
    Obtener un usuario específico por ID
    """
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    return user

# -----------------------------
# UPDATE USER (NUEVA VERSIÓN)
# -----------------------------
@router.put("/{user_id}", response_model=UserResponse)
def update_user(
    user_id: int, 
    user_data: UserUpdate, 
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)  # Cambiado: cualquier usuario autenticado
):
    """
    Actualizar un usuario existente
    Permite que:
    1. Los admins actualicen cualquier usuario (incluyendo role, is_active)
    2. Los usuarios actualicen su propio perfil (pero NO role, is_active)
    """
    # Buscar usuario a actualizar
    target_user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Verificar permisos
    is_admin = current_user.role == "admin"
    is_self = current_user.id == target_user.id
    
    if not (is_admin or is_self):
        raise HTTPException(
            status_code=403, 
            detail="No tiene permisos para actualizar este usuario"
        )
    
    # Si NO es admin y NO es su propio usuario, no puede cambiar role/is_active
    if not is_admin:
        # Remover campos que solo admin puede cambiar
        update_dict = user_data.dict(exclude_unset=True)
        if "role" in update_dict:
            raise HTTPException(
                status_code=403, 
                detail="No tiene permisos para cambiar el rol"
            )
        if "is_active" in update_dict:
            raise HTTPException(
                status_code=403, 
                detail="No tiene permisos para activar/desactivar usuarios"
            )
    
    # Verificar duplicados de email/username
    if user_data.email and user_data.email != target_user.email:
        existing_user = db.query(User).filter(
            User.email == user_data.email, 
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="El email ya está registrado por otro usuario"
            )
    
    if user_data.username and user_data.username != target_user.username:
        existing_user = db.query(User).filter(
            User.username == user_data.username, 
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="El username ya está registrado por otro usuario"
            )
    
    update_data = user_data.dict(exclude_unset=True)

    # Hash password si se actualiza
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = get_password_hash(update_data["password"])
        del update_data["password"]
    
    # Actualizar campos
    for field, value in update_data.items():
        if value is not None:
            setattr(target_user, field, value)
    
    db.commit()
    db.refresh(target_user)
    return target_user

# -----------------------------
# UPDATE PROFILE (Solo datos básicos, sin role/is_active)
# -----------------------------
@router.put("/{user_id}/profile", response_model=UserResponse)
def update_user_profile(
    user_id: int, 
    profile_data: ProfileUpdate,  # Usa ProfileUpdate que no incluye role/is_active
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Actualizar perfil de usuario (sin permisos de admin)
    Solo permite actualizar email, username, full_name, password
    """
    # Buscar usuario
    target_user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    # Solo puede actualizar su propio perfil
    if current_user.id != target_user.id:
        raise HTTPException(
            status_code=403, 
            detail="Solo puede actualizar su propio perfil"
        )
    
    # Verificar duplicados
    if profile_data.email and profile_data.email != target_user.email:
        existing_user = db.query(User).filter(
            User.email == profile_data.email, 
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="El email ya está registrado por otro usuario"
            )
    
    if profile_data.username and profile_data.username != target_user.username:
        existing_user = db.query(User).filter(
            User.username == profile_data.username, 
            User.id != user_id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="El username ya está registrado por otro usuario"
            )
    
    update_data = profile_data.dict(exclude_unset=True)
    
    # Hash password si se actualiza
    if "password" in update_data and update_data["password"]:
        update_data["hashed_password"] = get_password_hash(update_data["password"])
        del update_data["password"]
    
    # Actualizar campos
    for field, value in update_data.items():
        if value is not None:
            setattr(target_user, field, value)
    
    db.commit()
    db.refresh(target_user)
    return target_user

# -----------------------------
# CHANGE PASSWORD
# -----------------------------
@router.post("/{user_id}/change-password", response_model=Dict[str, str])
def change_user_password(
    user_id: int,
    password_data: Dict[str, str],  # {"current_password": "", "new_password": ""}
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """
    Cambiar contraseña de usuario
    - El usuario puede cambiar su propia contraseña
    - El admin puede cambiar cualquier contraseña sin saber la actual
    """
    # Buscar usuario
    target_user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not target_user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    current_password = password_data.get("current_password")
    new_password = password_data.get("new_password")
    
    if not new_password:
        raise HTTPException(status_code=400, detail="Debe proporcionar la nueva contraseña")
    
    # Verificar permisos
    is_admin = current_user.role == "admin"
    is_self = current_user.id == target_user.id
    
    if not (is_admin or is_self):
        raise HTTPException(
            status_code=403, 
            detail="No tiene permisos para cambiar esta contraseña"
        )
    
    # Si es el propio usuario (no admin), verificar contraseña actual
    if is_self and not is_admin:
        if not current_password:
            raise HTTPException(
                status_code=400, 
                detail="Debe proporcionar su contraseña actual"
            )
        
        if not verify_password(current_password, target_user.hashed_password):
            raise HTTPException(
                status_code=400, 
                detail="Contraseña actual incorrecta"
            )
    
    # Cambiar contraseña
    target_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Contraseña actualizada exitosamente"}

# -----------------------------
# SOFT DELETE (solo admin)
# -----------------------------
@router.delete("/{user_id}", response_model=UserResponse)
def delete_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(admin_required)
):
    """
    Soft delete: desactivar usuario (solo admin)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if not user.is_active:
        raise HTTPException(status_code=400, detail="El usuario ya está inactivo")
    
    user.is_active = False
    db.commit()
    db.refresh(user)
    return user

# -----------------------------
# HARD DELETE (solo admin)
# -----------------------------
@router.delete("/{user_id}/hard", response_model=Dict[str, Any])
def hard_delete_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(admin_required)
):
    """
    Eliminar físicamente un usuario (solo admin)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    db.delete(user)
    db.commit()
    return {"message": "Usuario eliminado permanentemente", "user_id": user_id}

# -----------------------------
# ACTIVATE USER (solo admin)
# -----------------------------
@router.patch("/{user_id}/activate", response_model=UserResponse)
def activate_user(
    user_id: int, 
    db: Session = Depends(get_db), 
    current_user: User = Depends(admin_required)
):
    """
    Reactivar usuario desactivado (solo admin)
    """
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    if user.is_active:
        raise HTTPException(status_code=400, detail="El usuario ya está activo")
    
    user.is_active = True
    db.commit()
    db.refresh(user)
    return user

# -----------------------------
# UPDATE ROLE (solo admin)
# -----------------------------
@router.put("/{user_id}/role", response_model=UserResponse)
def update_user_role(
    user_id: int, 
    role_data: Dict[str, str],  # {"role": "admin" | "user"}
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
):
    """
    Cambiar el rol de un usuario (solo admin)
    """
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()
    if not user:
        raise HTTPException(status_code=404, detail="Usuario no encontrado")
    
    new_role = role_data.get("role")
    if new_role not in ["admin", "user"]:
        raise HTTPException(status_code=400, detail="Rol inválido. Debe ser 'admin' o 'user'")
    
    user.role = new_role
    db.commit()
    db.refresh(user)
    return user

# -----------------------------
# GET CURRENT USER (conveniencia)
# -----------------------------
@router.get("/me/current", response_model=UserResponse)
def get_current_user_profile(current_user: User = Depends(get_current_user)):
    """
    Obtener el perfil del usuario actual
    """
    return current_user