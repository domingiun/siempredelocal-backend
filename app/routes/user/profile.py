# backend/app/routes/user/profile.py
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File
from sqlalchemy.orm import Session
from typing import Dict, Any
import os

from app.db import get_db
from app.models.user.user import User
from app.schemas.user.user import UserResponse, UserUpdate, ProfileUpdate
from app.core.security import get_password_hash, get_current_user
from app.utils.file_upload import (
    ALLOWED_EXTENSIONS, validate_image_mime,
    read_with_size_limit, generate_safe_filename,
)
from app.utils.storage import upload_file, delete_file, extract_filename_from_url

router = APIRouter(prefix="/profile", tags=["profile"])

AVATAR_FOLDER = "avatars"

# -----------------------------
# GET CURRENT USER PROFILE
# -----------------------------
@router.get("/me", response_model=UserResponse)
def get_my_profile(current_user: User = Depends(get_current_user)):
    """Obtener el perfil del usuario actual"""
    return current_user

# -----------------------------
# UPDATE CURRENT USER PROFILE
# -----------------------------
@router.put("/me", response_model=UserResponse)
def update_my_profile(
    profile_data: ProfileUpdate,  # Usamos ProfileUpdate que no incluye 'role'
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Actualizar el perfil del usuario actual"""
    
    # Verificar duplicados de email/username
    if profile_data.email and profile_data.email != current_user.email:
        existing_user = db.query(User).filter(
            User.email == profile_data.email, 
            User.id != current_user.id
        ).first()
        if existing_user:
            raise HTTPException(
                status_code=400, 
                detail="El email ya está registrado por otro usuario"
            )
    
    if profile_data.username and profile_data.username != current_user.username:
        existing_user = db.query(User).filter(
            User.username == profile_data.username, 
            User.id != current_user.id
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
            setattr(current_user, field, value)
    
    db.commit()
    db.refresh(current_user)
    return current_user

# -----------------------------
# UPLOAD AVATAR
# -----------------------------
@router.post("/me/avatar", response_model=UserResponse)
async def upload_my_avatar(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Subir avatar del usuario actual"""
    # Validar extensión
    file_extension = os.path.splitext(file.filename or "")[1].lower()
    if file_extension not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Formato no permitido. Use: {', '.join(ALLOWED_EXTENSIONS)}"
        )

    # Leer con límite de tamaño (A2)
    file_data = await read_with_size_limit(file)

    # Validar magic bytes reales (A1)
    validate_image_mime(file_data[:16], file_extension)

    # Nombre no predecible (M1)
    filename = generate_safe_filename(file_extension)

    # C8: Subir a Supabase Storage (persistente, no se pierde en redeploy)
    try:
        public_url = upload_file(
            folder=AVATAR_FOLDER,
            filename=filename,
            file_data=file_data,
            content_type=file.content_type or "image/jpeg",
        )
    except Exception:
        raise HTTPException(status_code=500, detail="Error al subir el archivo")

    # Eliminar avatar anterior de Supabase si existe
    if current_user.avatar_url:
        old_filename = extract_filename_from_url(current_user.avatar_url)
        delete_file(AVATAR_FOLDER, old_filename)

    current_user.avatar_url = public_url
    db.commit()
    db.refresh(current_user)
    return current_user

# -----------------------------
# CHANGE PASSWORD
# -----------------------------
@router.post("/change-password", response_model=Dict[str, str])
def change_password(
    password_data: Dict[str, str],  # {"current_password": "", "new_password": ""}
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    """Cambiar contraseña del usuario actual"""
    from app.core.security import verify_password
    
    current_password = password_data.get("current_password")
    new_password = password_data.get("new_password")
    
    if not current_password or not new_password:
        raise HTTPException(
            status_code=400, 
            detail="Debe proporcionar la contraseña actual y la nueva"
        )
    
    # Verificar contraseña actual
    if not verify_password(current_password, current_user.hashed_password):
        raise HTTPException(
            status_code=400, 
            detail="Contraseña actual incorrecta"
        )
    
    # Actualizar contraseña
    current_user.hashed_password = get_password_hash(new_password)
    db.commit()
    
    return {"message": "Contraseña actualizada exitosamente"}
