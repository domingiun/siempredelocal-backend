# backend/app/schemas/bet/UserWallet.py
from pydantic import BaseModel

class UserWalletBase(BaseModel):
    credits: int = 0
    balance_cop: int = 0

class UserWalletCreate(UserWalletBase):
    user_id: int

class UserWalletRead(UserWalletBase):
    id: int
    user_id: int
    balance_PTS: int = 0

    class Config:
        from_attributes = True
