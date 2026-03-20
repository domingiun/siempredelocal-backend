# backend/app/routes/bet/UserWallet.py
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select
from app.db import get_db
from app.models.bet.UserWallet import UserWallet
from app.schemas.bet.UserWallet import UserWalletRead
from app.routes.bet.transactions import purchase_credits
from app.schemas.bet.transactions import PurchaseCreditsRequest, PurchaseCreditsResponse

router = APIRouter(prefix="/wallets", tags=["UserWallet"])

# Consultar Mi Cajón de usuario
@router.get("/{user_id}", response_model=UserWalletRead)
def get_wallet(user_id: int, session: Session = Depends(get_db)):
    wallet = session.execute(
        select(UserWallet).where(UserWallet.user_id == user_id)
    ).scalars().first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Mi Cajón no encontrado")
    return {
        "id": wallet.id,
        "user_id": wallet.user_id,
        "credits": wallet.credits,
        "balance_cop": wallet.balance_cop,
        "balance_PTS": wallet.balance_cop
    }

# Recargar créditos (agregar a Mi Cajón)
@router.post("/buy", response_model=UserWalletRead)
def buy_credits(user_id: int, credits: int, session: Session = Depends(get_db)):
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

router.post("/buy-credits", response_model=PurchaseCreditsResponse)
def buy_credits(
    request: PurchaseCreditsRequest,
    user_id: int,
    session: Session = Depends(get_db)
):
    """
    Recargar créditos (nueva versión con transacciones)
    """
    return purchase_credits(request, user_id, session)
