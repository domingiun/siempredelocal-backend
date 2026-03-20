# backend/repair_prize_rollover.py
"""
Corrige el premio de una fecha acumulando premios pendientes de fechas anteriores
y entrega el delta faltante al ganador (o ganadores por empate).

Uso:
  python repair_prize_rollover.py 4
"""
import sys
from sqlalchemy import func
from app.db import SessionLocal
from app.models.bet.BetDate import BetDate
from app.models.bet.Bet import Bet
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from app.models.user.password_reset_token import PasswordResetToken  # noqa: F401
from app.services.transaction_service import TransactionService


def main():
    if len(sys.argv) < 2:
        print("ERROR: Debes pasar bet_date_id. Ej: python repair_prize_rollover.py 4")
        sys.exit(1)

    bet_date_id = int(sys.argv[1])
    session = SessionLocal()
    try:
        betdate = session.query(BetDate).get(bet_date_id)
        if not betdate:
            print(f"ERROR: bet_date_id {bet_date_id} no existe")
            sys.exit(1)

        # Calcular carryover desde fechas anteriores con premio pendiente
        carryover_dates = (
            session.query(BetDate)
            .filter(BetDate.id < bet_date_id)
            .filter((BetDate.prize_cop > 0) | (BetDate.accumulated_prize > 0))
            .order_by(BetDate.id)
            .all()
        )
        carryover_total = sum(d.prize_cop + d.accumulated_prize for d in carryover_dates)

        expected_total = betdate.prize_cop + betdate.accumulated_prize + carryover_total

        # Total ya entregado en esta fecha (PRIZE_WIN)
        awarded_total = (
            session.query(func.coalesce(func.sum(Transaction.amount_cop), 0))
            .join(Bet, Bet.id == Transaction.reference_id)
            .filter(
                Transaction.transaction_type == TransactionType.PRIZE_WIN,
                Transaction.status == TransactionStatus.COMPLETED,
                Bet.bet_date_id == bet_date_id,
            )
            .scalar()
        ) or 0

        delta = expected_total - awarded_total

        print(f"BETDATE {bet_date_id} expected_total={expected_total} awarded_total={awarded_total} delta={delta}")

        if delta <= 0:
            print("Nada por corregir.")
            # Limpiar carryover pendiente
            for d in carryover_dates:
                d.prize_cop = 0
                d.accumulated_prize = 0
            session.commit()
            return

        # Determinar ganadores (top points) con mínimo 13
        top_bet = (
            session.query(Bet)
            .filter(Bet.bet_date_id == bet_date_id)
            .order_by(Bet.points.desc())
            .first()
        )
        if not top_bet or top_bet.points < 13:
            print("No hay ganador (>=13). No se entrega delta.")
            return

        top_points = top_bet.points
        winners = (
            session.query(Bet)
            .filter(Bet.bet_date_id == bet_date_id, Bet.points == top_points)
            .all()
        )

        # Reparto del delta entre ganadores
        base_amount = delta // len(winners)
        remainder = delta % len(winners)

        for idx, winner in enumerate(winners):
            prize_amount = base_amount + (1 if idx < remainder else 0)
            TransactionService.award_prize(
                session=session,
                user_id=winner.user_id,
                bet_date_id=bet_date_id,
                prize_amount=prize_amount,
                bet_id=winner.id
            )

        # Limpiar carryover pendiente y saldo de premio en la fecha
        for d in carryover_dates:
            d.prize_cop = 0
            d.accumulated_prize = 0
        betdate.prize_cop = 0
        betdate.accumulated_prize = 0

        session.commit()
        print("OK: Delta entregado y carryover limpiado.")
    except Exception as exc:
        session.rollback()
        print(f"ERROR: {exc}")
        raise
    finally:
        session.close()


if __name__ == "__main__":
    main()

