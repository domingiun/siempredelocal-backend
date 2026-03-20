# backend/app/routes/user/auth.py
from fastapi import APIRouter, Depends, HTTPException, status
from datetime import datetime, timedelta
import hashlib
import os
import secrets
from fastapi.security import OAuth2PasswordRequestForm
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import text

from app.db import get_db
from app.models.user.user import User
from app.models.user.password_reset_token import PasswordResetToken
from app.schemas.user.user import UserCreate, UserResponse, Token, PasswordResetRequest, PasswordResetConfirm
from app.core.security import (
    verify_password,
    get_password_hash,
    create_access_token,
    get_current_user
)

router = APIRouter(prefix="/auth", tags=["authentication"])

def _hash_reset_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()

# backend/app/routes/user/auth.py - actualizar authenticate_user
def authenticate_user(db: Session, username: str, password: str):
    """Autenticar usuario verificando username/email y password"""
    # Buscar por username O email
    user = db.query(User).filter(
        (User.username == username) | (User.email == username)
    ).first()
    
    if not user:
        return None
    
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Usuario inactivo"
        )
    
    # ✅ Usar verify_password del core.security
    if not verify_password(password, user.hashed_password):
        return None
    
    return user

@router.post("/register", response_model=UserResponse)
def register(user_data: UserCreate, db: Session = Depends(get_db)):

    db_user = db.query(User).filter(
        (User.email == user_data.email) | (User.username == user_data.username)
    ).first()

    if db_user:
        raise HTTPException(status_code=400, detail="Email o username ya registrado")

    hashed_password = get_password_hash(user_data.password)

    def build_user():
        return User(
            email=user_data.email,
            username=user_data.username,
            full_name=user_data.full_name,
            phone=user_data.phone,
            hashed_password=hashed_password
        )

    db_user = build_user()
    db.add(db_user)

    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        error_text = str(exc.orig).lower()

        # Secuencia desincronizada (común tras migraciones con IDs explícitos)
        if "users_pkey" in error_text:
            db.execute(text(
                "SELECT setval(pg_get_serial_sequence('users','id'), "
                "COALESCE((SELECT MAX(id) FROM users), 0) + 1, false)"
            ))
            db.commit()

            db_user = build_user()
            db.add(db_user)
            db.commit()
        elif "users_email_key" in error_text or "users_username_key" in error_text:
            raise HTTPException(status_code=400, detail="Email o username ya registrado")
        else:
            raise HTTPException(status_code=500, detail="Error de integridad al registrar usuario")

    db.refresh(db_user)

    return db_user

@router.post("/login")
def login(form_data: OAuth2PasswordRequestForm = Depends(), db: Session = Depends(get_db)):
    user = authenticate_user(db, form_data.username, form_data.password)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Credenciales incorrectas",
            headers={"WWW-Authenticate": "Bearer"},
        )
    access_token = create_access_token(
        data={"sub": user.username, "role": user.role, "id": user.id}
    )
    return {
        "access_token": access_token,
        "token_type": "bearer",
        "user": UserResponse.model_validate(user)
    }

@router.get("/me", response_model=UserResponse)
def read_users_me(current_user: User = Depends(get_current_user)):
    return current_user


@router.post("/forgot-password")
def forgot_password(request: PasswordResetRequest, db: Session = Depends(get_db)):
    user = None
    contact_value = None

    if request.channel == "email":
        user = db.query(User).filter(User.email == request.email).first()
        contact_value = request.email
    elif request.channel == "whatsapp":
        user = db.query(User).filter(User.phone == request.phone).first()
        contact_value = request.phone

    response = {
        "message": "Si la cuenta existe, recibiras instrucciones para restablecer tu contrasena."
    }

    if not user:
        return response

    now = datetime.utcnow()
    expires_at = now + timedelta(minutes=30)

    db.query(PasswordResetToken).filter(
        PasswordResetToken.user_id == user.id,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > now
    ).update({"used_at": now}, synchronize_session=False)

    token = secrets.token_urlsafe(32)
    token_hash = _hash_reset_token(token)

    reset_record = PasswordResetToken(
        user_id=user.id,
        channel=request.channel,
        token_hash=token_hash,
        requested_to=contact_value,
        expires_at=expires_at
    )
    db.add(reset_record)
    db.commit()

    # TODO: Enviar email o WhatsApp con el link/token
    # Modo dev: exponer link solo si DEBUG=true
    if os.getenv("DEBUG", "").lower() == "true":
        frontend_url = os.getenv("FRONTEND_URL", "http://localhost:5173")
        response["dev_reset_link"] = f"{frontend_url}/reset-password?token={token}"

    return response


@router.post("/reset-password")
def reset_password(request: PasswordResetConfirm, db: Session = Depends(get_db)):
    token_hash = _hash_reset_token(request.token)
    now = datetime.utcnow()

    token_row = db.query(PasswordResetToken).filter(
        PasswordResetToken.token_hash == token_hash,
        PasswordResetToken.used_at.is_(None),
        PasswordResetToken.expires_at > now
    ).order_by(PasswordResetToken.id.desc()).first()

    if not token_row:
        raise HTTPException(status_code=400, detail="Token invalido o expirado")

    user = db.query(User).filter(User.id == token_row.user_id).first()
    if not user or not user.is_active:
        raise HTTPException(status_code=400, detail="Usuario invalido")

    user.hashed_password = get_password_hash(request.new_password)
    token_row.used_at = now
    db.commit()

    return {"message": "Contrasena actualizada correctamente"}
