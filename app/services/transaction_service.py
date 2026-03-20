# backend/app/services/transaction_service.py
from datetime import datetime
from typing import Optional, Dict, Any
from sqlalchemy.orm import Session
from sqlalchemy import exc
from sqlalchemy import text
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from app.models.bet.UserWallet import UserWallet
from app.models.bet.BetPlan import BetPlan

class TransactionService:

    @staticmethod
    def _sync_pk_sequences(session: Session) -> None:
        """
        Re-sincroniza secuencias PK en PostgreSQL (útil tras migraciones con IDs explícitos).
        """
        session.execute(text(
            "SELECT setval(pg_get_serial_sequence('user_wallets','id'), "
            "COALESCE((SELECT MAX(id) FROM user_wallets), 0) + 1, false)"
        ))
        session.execute(text(
            "SELECT setval(pg_get_serial_sequence('transactions','id'), "
            "COALESCE((SELECT MAX(id) FROM transactions), 0) + 1, false)"
        ))
    
    @staticmethod
    def create_transaction(
        session: Session,
        user_id: int,
        transaction_type: TransactionType,
        amount_cop: int = 0,
        amount_credits: int = 0,
        fee_cop: int = 0,
        reference_id: Optional[int] = None,
        reference_type: Optional[str] = None,
        description: Optional[str] = None,
        payment_method: Optional[str] = None,
        payment_reference: Optional[str] = None
    ) -> Transaction:
        """
        Crear una nueva transacción
        """
        # Evita errores duplicate key en PK por secuencias desfasadas.
        TransactionService._sync_pk_sequences(session)

        # Buscar wallet del usuario
        wallet = session.query(UserWallet).filter_by(user_id=user_id).first()
        if not wallet:
            wallet = UserWallet(
                user_id=user_id,
                credits=0,
                balance_cop=0,
                total_credits_purchased=0,
                total_prizes_won=0
            )
            session.add(wallet)
            session.flush() 
        
        # Calcular monto neto
        net_amount_cop = amount_cop - fee_cop
        
        # Crear transacción
        transaction = Transaction(
            user_id=user_id,
            wallet_id=wallet.id,
            transaction_type=transaction_type,
            status=TransactionStatus.PENDING,
            amount_cop=amount_cop,
            amount_credits=amount_credits,
            fee_cop=fee_cop,
            net_amount_cop=net_amount_cop,
            reference_id=reference_id,
            reference_type=reference_type,
            description=description,
            payment_method=payment_method,
            payment_reference=payment_reference
        )
        
        session.add(transaction)
        session.flush()  # Para obtener el ID
        
        return transaction
    
    @staticmethod
    def complete_transaction(
        session: Session,
        transaction_id: int,
        update_wallet: bool = True
    ) -> Transaction:
        """
        Completar una transacción y actualizar wallet si es necesario
        """
        transaction = session.query(Transaction).get(transaction_id)
        if not transaction:
            raise ValueError(f"Transacción {transaction_id} no encontrada")
        
        if transaction.status == TransactionStatus.COMPLETED:
            return transaction
        
        # Actualizar wallet si es necesario
        if update_wallet:
            wallet = session.query(UserWallet).get(transaction.wallet_id)
            if not wallet:
                raise ValueError(f"Wallet {transaction.wallet_id} no encontrada")
            
            # Aplicar transacción según tipo
            if transaction.transaction_type == TransactionType.CREDIT_PURCHASE:
                wallet.credits += transaction.amount_credits
                wallet.total_credits_purchased += transaction.amount_credits
                
            elif transaction.transaction_type == TransactionType.BET_PLACEMENT:
                if wallet.credits < transaction.amount_credits:
                    raise ValueError("Créditos insuficientes")
                wallet.credits -= transaction.amount_credits
                
            elif transaction.transaction_type == TransactionType.PRIZE_WIN:
                # Premios se cargan como puntos disponibles (balance_cop)
                wallet.balance_cop += transaction.amount_cop
                wallet.total_prizes_won += transaction.amount_cop
                
            elif transaction.transaction_type == TransactionType.CREDIT_CONVERSION:
                wallet.credits -= transaction.amount_credits
                wallet.balance_cop += transaction.amount_cop
                
            elif transaction.transaction_type == TransactionType.REFUND:
                if transaction.amount_credits > 0:
                    wallet.credits += transaction.amount_credits
                if transaction.amount_cop > 0:
                    wallet.balance_cop += transaction.amount_cop
            elif transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT:
                if transaction.amount_credits:
                    wallet.credits += transaction.amount_credits
                if transaction.amount_cop:
                    wallet.balance_cop += transaction.amount_cop
        
        # Marcar como completada
        transaction.status = TransactionStatus.COMPLETED
        transaction.completed_at = datetime.now()
        
        session.flush()
        return transaction
    
    @staticmethod
    def purchase_credits(
        session: Session,
        user_id: int,
        plan_id: int,
        payment_method: str = "credit_card",
        payment_reference: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Recargar créditos usando un plan (queda pendiente de aprobación)
        """
        # Obtener plan
        plan = session.query(BetPlan).get(plan_id)
        if not plan or not plan.is_active:
            raise ValueError("Plan no disponible")
        
        # Crear transacción PENDIENTE 
        transaction = TransactionService.create_transaction(
            session=session,
            user_id=user_id,
            transaction_type=TransactionType.CREDIT_PURCHASE,
            amount_cop=plan.final_price,
            amount_credits=plan.credits,
            fee_cop=0,
            reference_id=plan.id,
            reference_type="bet_plan",
            description=f"Solicitud de recarga de {plan.credits} créditos - Plan {plan.name}",
            payment_method=payment_method,
            payment_reference=payment_reference
        )

        # Persistir la transacción pendiente
        session.commit()

        return {
            "transaction_id": transaction.id,
            "credits_added": plan.credits,
            "total_paid": plan.final_price,  # Corregir a final_price
            "prize_contribution": plan.prize_contribution * plan.credits,
            "status": transaction.status.value,  # Devolver como string
            "new_balance": transaction.wallet.credits  # Saldo actual (sin cambios)
        }
        
    @staticmethod
    def place_bet_transaction(
        session: Session,
        user_id: int,
        bet_id: int,
        bet_date_id: int,
        credits_used: int
    ) -> Dict[str, Any]:
        """
        Registrar transacción por pronósticos
        """
        # Calcular contribución automáticamente ($1,950 por crédito)
        PRIZE_CONTRIBUTION_PER_CREDIT = 1950
        prize_contribution = PRIZE_CONTRIBUTION_PER_CREDIT * credits_used
        
        # Crear transacción de apuesta
        transaction = TransactionService.create_transaction(
            session=session,
            user_id=user_id,
            transaction_type=TransactionType.BET_PLACEMENT,
            amount_credits=credits_used,
            amount_cop=prize_contribution,
            reference_id=bet_id,
            reference_type="bet",
            description=f"Pronósticos en fecha {bet_date_id} - {credits_used} crédito(s)"
        )
            
        # Completar transacción (actualiza wallet)
        TransactionService.complete_transaction(session, transaction.id)
         
        return {
            "transaction_id": transaction.id,
            "credits_deducted": credits_used,
            "prize_contribution": prize_contribution,
            "new_credits_balance": transaction.wallet.credits,
            "profit_to_house": (5000 - 1950) * credits_used  # $3050 por crédito
        }
    
    @staticmethod
    def award_prize(
        session: Session,
        user_id: int,
        bet_date_id: int,
        prize_amount: int,
        bet_id: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        Registrar transacción por premio ganado
        """
        # Crear transacción de premio
        transaction = TransactionService.create_transaction(
            session=session,
            user_id=user_id,
            transaction_type=TransactionType.PRIZE_WIN,
            amount_cop=prize_amount,
            reference_id=bet_id,
            reference_type="bet",
            description=f"Premio ganado en fecha {bet_date_id}"
        )
        
        # Completar transacción (actualiza wallet)
        TransactionService.complete_transaction(session, transaction.id)
        
        return {
            "transaction_id": transaction.id,
            "prize_awarded": prize_amount,
            "new_balance_cop": transaction.wallet.balance_cop,
            "total_prizes_won": transaction.wallet.total_prizes_won
        }
    
    @staticmethod
    def convert_credits_to_cash(
        session: Session,
        user_id: int,
        credits_to_convert: int
    ) -> Dict[str, Any]:
        """
        Solicitar conversión de créditos a dinero (retiro manual)
        """
        # Configuración del sistema
        CONVERSION_RATE = 4500  # COP por crédito
        WITHDRAWAL_FEE_PERCENT = 5

        # Obtener wallet
        wallet = session.query(UserWallet).filter_by(user_id=user_id).first()
        if not wallet:
            raise ValueError("Wallet no encontrada")

        if credits_to_convert > wallet.credits:
            raise ValueError("Créditos insuficientes")

        # Cálculos
        gross_amount = credits_to_convert * CONVERSION_RATE
        fee = int(gross_amount * (WITHDRAWAL_FEE_PERCENT / 100))
        net_amount = gross_amount - fee

        # Crear transacción PENDING (NO actualizar wallet aún)
        transaction = TransactionService.create_transaction(
            session=session,
            user_id=user_id,
            transaction_type=TransactionType.CREDIT_CONVERSION,
            amount_cop=net_amount,
            amount_credits=credits_to_convert,
            fee_cop=fee,
            reference_type="credit_conversion",
            description=f"Solicitud de conversión de {credits_to_convert} créditos",
            payment_method="nequi"
        )

        session.commit()

        return {
            "transaction_id": transaction.id,
            "credits_converted": credits_to_convert,
            "amount_received": net_amount,
            "fee": fee,
            "status": transaction.status
        }

    
    @staticmethod
    def get_user_transactions(
        session: Session,
        user_id: int,
        limit: int = 50,
        offset: int = 0,
        transaction_type: Optional[TransactionType] = None
    ) -> list:
        """
        Obtener historial de transacciones de un usuario
        """
        query = session.query(Transaction).filter_by(user_id=user_id)
        
        if transaction_type:
            query = query.filter_by(transaction_type=transaction_type)
        
        query = query.order_by(Transaction.created_at.desc())
        query = query.offset(offset).limit(limit)
        
        return query.all()
    
@staticmethod
def approve_transaction(
    session: Session,
    transaction_id: int,
    admin_user_id: int
) -> Transaction:
    """
    Aprobar transacción pendiente (ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)
    if not transaction:
        raise ValueError("Transacción no encontrada")

    if transaction.status != TransactionStatus.PENDING:
        raise ValueError("La transacción no está pendiente")

    # Completar y aplicar a wallet
    TransactionService.complete_transaction(
        session=session,
        transaction_id=transaction.id,
        update_wallet=True
    )

    transaction.description = (
        transaction.description or ""
    ) + f" | Aprobada por admin {admin_user_id}"

    session.commit()
    return transaction

@staticmethod
def reject_transaction(
    session: Session,
    transaction_id: int,
    admin_user_id: int,
    reason: Optional[str] = None
) -> Transaction:
    """
    Rechazar transacción pendiente (ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)
    if not transaction:
        raise ValueError("Transacción no encontrada")

    if transaction.status != TransactionStatus.PENDING:
        raise ValueError("La transacción no está pendiente")

    transaction.status = TransactionStatus.CANCELLED
    transaction.description = (
        transaction.description or ""
    ) + f" | Rechazada por admin {admin_user_id}. Motivo: {reason or 'No especificado'}"

    session.commit()
    return transaction
