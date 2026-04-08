# backend/app/routes/bet/UserWallet.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.models.bet.UserWallet import UserWallet
from app.schemas.bet.UserWallet import UserWalletRead
from app.core.security import get_current_user
from app.core.dependencies import get_current_admin_user
from app.models.user.user import User

router = APIRouter(prefix="/wallets", tags=["UserWallet"])


# Consultar Mi Cuenta de usuario
@router.get("/{user_id}", response_model=UserWalletRead)
def get_wallet(
    user_id: int,
    session: Session = Depends(get_db),
    current_user: User = Depends(get_current_user)
):
    # Solo el propio usuario o un admin puede ver el wallet
    if current_user.id != user_id and current_user.role.upper() != "ADMIN":
        raise HTTPException(status_code=403, detail="No tienes permiso para ver este cajón")

    wallet = session.execute(
        select(UserWallet).where(UserWallet.user_id == user_id)
    ).scalars().first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Mi Cuenta no encontrada")
    return {
        "id": wallet.id,
        "user_id": wallet.user_id,
        "credits": wallet.credits,
        "balance_cop": wallet.balance_cop,
        "balance_PTS": wallet.balance_cop
    }


# Recargar créditos manualmente (solo ADMIN — uso interno/debug)
@router.post("/buy", response_model=UserWalletRead)
def buy_credits(
    user_id: int,
    credits: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    if credits <= 0:
        raise HTTPException(status_code=400, detail="La cantidad de créditos debe ser positiva")

    wallet = session.execute(
        select(UserWallet).where(UserWallet.user_id == user_id)
    ).scalars().first()

    if not wallet:
        wallet = UserWallet(user_id=user_id, credits=credits)
        session.add(wallet)
    else:
        wallet.credits += credits

    session.commit()
    session.refresh(wallet)
    return wallet
