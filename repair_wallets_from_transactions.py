# backend/repair_wallets_from_transactions.py
"""
Recalcula los saldos de Mi Cuenta (credits y balance_cop) a partir de las
transacciones COMPLETED. Útil para corregir premios ya finalizados que no
se reflejaron en Puntos disponibles.
"""
from sqlalchemy import asc
from app.db import SessionLocal
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from app.models.bet.UserWallet import UserWallet
# Import para registrar relaciones de User
from app.models.user.password_reset_token import PasswordResetToken  # noqa: F401


def rebuild_wallets():
    session = SessionLocal()
    try:
        wallets = session.query(UserWallet).all()

        for wallet in wallets:
            # Reset
            wallet.credits = 0
            wallet.balance_cop = 0
            wallet.total_credits_purchased = 0
            wallet.total_prizes_won = 0

            transactions = (
                session.query(Transaction)
                .filter(
                    Transaction.user_id == wallet.user_id,
                    Transaction.status == TransactionStatus.COMPLETED
                )
                .order_by(asc(Transaction.created_at), asc(Transaction.id))
                .all()
            )

            for tx in transactions:
                if tx.transaction_type == TransactionType.CREDIT_PURCHASE:
                    wallet.credits += tx.amount_credits
                    wallet.total_credits_purchased += tx.amount_credits

                elif tx.transaction_type == TransactionType.BET_PLACEMENT:
                    wallet.credits -= tx.amount_credits

                elif tx.transaction_type == TransactionType.PRIZE_WIN:
                    wallet.balance_cop += tx.amount_cop
                    wallet.total_prizes_won += tx.amount_cop

                elif tx.transaction_type == TransactionType.CREDIT_CONVERSION:
                    wallet.credits -= tx.amount_credits
                    wallet.balance_cop += tx.amount_cop

                elif tx.transaction_type == TransactionType.REFUND:
                    if tx.amount_credits:
                        wallet.credits += tx.amount_credits
                    if tx.amount_cop:
                        wallet.balance_cop += tx.amount_cop

                elif tx.transaction_type == TransactionType.ADMIN_ADJUSTMENT:
                    wallet.credits += tx.amount_credits

            session.flush()

        session.commit()
        print("OK: Saldos recalculados para todas las wallets.")
    except Exception as exc:
        session.rollback()
        print(f"ERROR: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    rebuild_wallets()
