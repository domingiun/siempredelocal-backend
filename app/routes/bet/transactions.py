# backend/app/routes/bet/transactions.py
from fastapi import APIRouter, Depends, HTTPException, Body
from sqlalchemy import func
from sqlalchemy.orm import Session
from typing import List, Optional
from app.db import get_db
from app.services.transaction_service import TransactionService
from app.schemas.bet.transactions import (
    PurchaseCreditsRequest, PurchaseCreditsResponse, ConvertCreditsRequest,
    ConvertCreditsResponse, TransactionHistoryResponse, TransactionDetail,
    PointsToCreditsRequest, WithdrawPointsRequest
)
from app.models.bet.BetPlan import BetPlan
from app.models.bet.BetDate import BetDate
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from app.models.bet.UserWallet import UserWallet
from pydantic import BaseModel
from datetime import datetime
from app.core.dependencies import admin_required, get_current_admin_user
from app.models.user.user import User

router = APIRouter(prefix="/transactions", tags=["Transactions"])

class AdminCreditAdjustmentRequest(BaseModel):
    user_id: int
    credits: int
    reason: Optional[str] = None


@router.post("/purchase-credits", response_model=PurchaseCreditsResponse)
def purchase_credits(
    request: PurchaseCreditsRequest,
    user_id: int,
    session: Session = Depends(get_db)
):
    """
    Recargar créditos usando un plan específico
    """
    try:
        result = TransactionService.purchase_credits(
            session=session,
            user_id=user_id,
            plan_id=request.plan_id,
            payment_method=request.payment_method,
            payment_reference=request.payment_reference
        )
        
        return PurchaseCreditsResponse(
            success=True,
            message="Solicitud de recarga registrada. Pendiente de confirmación.",
            transaction_id=result["transaction_id"],
            credits_added=result["credits_added"],
            total_paid=result["total_paid"],
            prize_contribution=result["prize_contribution"],
            new_balance=result["new_balance"],
            timestamp=datetime.now()
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la recarga: {str(e)}")


@router.post("/convert-to-cash", response_model=ConvertCreditsResponse)
def convert_credits_to_cash(
    request: ConvertCreditsRequest,
    user_id: int,
    session: Session = Depends(get_db)
):
    """
    Convertir créditos a dinero en efectivo
    """
    try:
        result = TransactionService.convert_credits_to_cash(
            session=session,
            user_id=user_id,
            credits_to_convert=request.credits_to_convert,
            conversion_rate=request.conversion_rate or 4500
        )
        
        return ConvertCreditsResponse(
            success=True,
            message="Conversión exitosa",
            transaction_id=result["transaction_id"],
            credits_converted=result["credits_converted"],
            amount_received=result["amount_received"],
            fee=result["fee"],
            new_credits_balance=result["new_credits_balance"],
            new_cash_balance=result["new_cash_balance"],
            timestamp=datetime.now()
        )
        
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        session.rollback()
        raise HTTPException(status_code=500, detail=f"Error en la conversión: {str(e)}")


@router.post("/request/points-to-credits")
def request_points_to_credits(
    request: PointsToCreditsRequest,
    user_id: int,
    session: Session = Depends(get_db)
):
    """
    Solicitar conversión de puntos (balance) a créditos (requiere aprobación ADMIN)
    """
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

    credit_value = request.credit_value_pts or 5000
    if request.points_to_convert < credit_value:
        raise HTTPException(status_code=400, detail=f"Mínimo {credit_value} PTS para convertir a créditos")
    if request.points_to_convert % credit_value != 0:
        raise HTTPException(status_code=400, detail=f"Los puntos deben ser múltiplo de {credit_value} PTS")
    if request.points_to_convert > wallet.balance_cop:
        raise HTTPException(status_code=400, detail="Saldo de puntos insuficiente")

    credits_to_add = request.points_to_convert // credit_value

    transaction = TransactionService.create_transaction(
        session=session,
        user_id=user_id,
        transaction_type=TransactionType.ADMIN_ADJUSTMENT,
        amount_cop=-request.points_to_convert,
        amount_credits=credits_to_add,
        reference_type="points_to_credits",
        description=f"Solicitud canje de {request.points_to_convert} PTS a {credits_to_add} créditos",
        payment_method="points_to_credits"
    )

    session.commit()

    return {
        "success": True,
        "message": "Solicitud enviada. Pendiente de aprobación.",
        "transaction_id": transaction.id,
        "points_requested": request.points_to_convert,
        "credits_requested": credits_to_add,
        "status": transaction.status.value
    }


@router.post("/request/withdraw")
def request_withdraw_points(
    request: WithdrawPointsRequest,
    user_id: int,
    session: Session = Depends(get_db)
):
    """
    Solicitar retiro de puntos (requiere aprobación ADMIN)
    """
    wallet = session.query(UserWallet).filter_by(user_id=user_id).first()
    if not wallet:
        raise HTTPException(status_code=404, detail="Wallet no encontrada")

    if request.amount_pts < 20000:
        raise HTTPException(status_code=400, detail="El retiro mínimo es 20,000 PTS")
    if request.amount_pts > 1000000:
        raise HTTPException(status_code=400, detail="El retiro máximo es 1,000,000 PTS")
    if request.amount_pts > wallet.balance_cop:
        raise HTTPException(status_code=400, detail="Saldo de puntos insuficiente")

    transaction = TransactionService.create_transaction(
        session=session,
        user_id=user_id,
        transaction_type=TransactionType.ADMIN_ADJUSTMENT,
        amount_cop=-request.amount_pts,
        amount_credits=0,
        reference_type="withdrawal",
        description=f"Solicitud de retiro por {request.amount_pts} PTS",
        payment_method=request.payment_method.value if hasattr(request.payment_method, 'value') else str(request.payment_method)
    )

    session.commit()

    return {
        "success": True,
        "message": "Solicitud de retiro enviada. Pendiente de aprobación.",
        "transaction_id": transaction.id,
        "amount_requested": request.amount_pts,
        "status": transaction.status.value
    }


@router.get("/history/{user_id}", response_model=TransactionHistoryResponse)
def get_transaction_history(
    user_id: int,
    transaction_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db)
):
    """
    Obtener historial de transacciones de un usuario
    """
    try:
        # Convertir string a enum si se proporciona
        type_enum = None
        if transaction_type:
            try:
                type_enum = TransactionType(transaction_type)
            except ValueError:
                raise HTTPException(status_code=400, detail="Tipo de transacción inválido")
        
        transactions = TransactionService.get_user_transactions(
            session=session,
            user_id=user_id,
            limit=limit,
            offset=offset,
            transaction_type=type_enum
        )
        
        # Convertir a schema con campos adicionales
        transaction_list = []
        for trans in transactions:
            # Determinar amount y credits según tipo
            amount = 0
            credits_affected = 0
            
            if trans.transaction_type == TransactionType.CREDIT_PURCHASE:
                amount = -trans.amount_cop  # Negativo porque es gasto
                credits_affected = trans.amount_credits
            elif trans.transaction_type == TransactionType.PRIZE_WIN:
                amount = trans.net_amount_cop  # Positivo porque es ganancia
                credits_affected = 0
            elif trans.transaction_type == TransactionType.BET_PLACEMENT:
                amount = -5000  # Fijo: $5,000 COP por apuesta
                credits_affected = -1  # Siempre 1 crédito
            elif trans.transaction_type == TransactionType.CREDIT_CONVERSION:
                amount = trans.net_amount_cop  # Retiro positivo
                credits_affected = -trans.amount_credits  # Créditos reducidos
            elif trans.transaction_type == TransactionType.REFUND:
                amount = trans.amount_cop  # Reembolso positivo
                credits_affected = trans.amount_credits
            elif trans.transaction_type == TransactionType.ADMIN_ADJUSTMENT:
                amount = trans.amount_cop
                credits_affected = trans.amount_credits
            
            transaction_list.append(TransactionDetail(
                id=trans.id,
                transaction_type=trans.transaction_type.value,
                status=trans.status.value,
                amount_cop=trans.amount_cop,
                amount_credits=trans.amount_credits,
                fee_cop=trans.fee_cop,
                net_amount_cop=trans.net_amount_cop,
                description=trans.description,
                reference_id=trans.reference_id,
                reference_type=trans.reference_type,
                created_at=trans.created_at,
                completed_at=trans.completed_at,
                # ✅ CAMPOS NUEVOS PARA FRONTEND
                amount=amount,
                currency="COP",
                credits_affected=credits_affected
            ))
        
        # Obtener totales
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
        
        return TransactionHistoryResponse(
            user_id=user_id,
            total_transactions=len(transactions),
            total_spent=sum(t.amount_cop for t in transactions if t.amount_cop > 0),
            total_earned=sum(t.amount_cop for t in transactions 
                           if t.transaction_type == TransactionType.PRIZE_WIN),
            current_credits=wallet.credits if wallet else 0,
            current_balance_cop=wallet.balance_cop if wallet else 0,
            transactions=transaction_list
        )
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error al obtener historial: {str(e)}")


@router.get("/plans")
def get_available_plans(session: Session = Depends(get_db)):
    """
    Obtener planes de créditos disponibles
    """
    plans = session.query(BetPlan).filter_by(is_active=True).all()
    
    result = []
    for plan in plans:
        result.append({
            "id": plan.id,
            "name": plan.name,
            "credits": plan.credits,
            "base_price": plan.price_cop,
            "discount_percent": plan.discount_percent,
            "final_price": plan.final_price,
            "prize_contribution": plan.prize_contribution,
            "profit": plan.profit,
            "value_per_credit": plan.final_price / plan.credits if plan.credits > 0 else 0
        })
        
    
    return {"plans": result}

@router.post("/admin/transactions/{transaction_id}/approve")
def approve_credit_purchase(
    transaction_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Aprobar recarga de créditos (solo ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="La transacción no está pendiente")

    if transaction.transaction_type != TransactionType.CREDIT_PURCHASE:
        raise HTTPException(status_code=400, detail="Tipo de transacción inválido")

    TransactionService.complete_transaction(session, transaction.id)

    return {
        "success": True,
        "message": "Recarga de créditos aprobada",
        "transaction_id": transaction.id,
        "approved_by": admin_user.id
    }

@router.get("/admin/pending-credit-purchases")
def get_pending_credit_purchases(
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Listar recargass de créditos pendientes (solo ADMIN)
    """
    transactions = (
        session.query(Transaction)
        .filter(
            Transaction.transaction_type == TransactionType.CREDIT_PURCHASE,
            Transaction.status == TransactionStatus.PENDING
        )
        .order_by(Transaction.created_at.desc())
        .all()
    )

    result = []

    for t in transactions:
        result.append({
            "transaction_id": t.id,
            "user_id": t.user_id,
            "user_name": t.user.username if t.user else None,
            "user_full_name": t.user.full_name if t.user else None,
            "credits": t.amount_credits,
            "amount_cop": t.amount_cop,
            "payment_method": t.payment_method,
            "payment_reference": t.payment_reference,
            "created_at": t.created_at,
            "description": t.description
        })

    return {
        "total": len(result),
        "pending_purchases": result
    }

@router.post("/admin/approve-credit-purchase/{transaction_id}")
def approve_credit_purchase(
    transaction_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Aprobar recarga de créditos (ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    if transaction.transaction_type != TransactionType.CREDIT_PURCHASE:
        raise HTTPException(status_code=400, detail="No es una recarga de créditos")

    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="La transacción no está pendiente")

    # Completa la transacción y actualiza wallet
    TransactionService.complete_transaction(
        session=session,
        transaction_id=transaction.id,
        update_wallet=True
    )

    session.commit()

    return {
        "success": True,
        "message": "Recarga de créditos aprobada",
        "transaction_id": transaction.id,
        "credits_added": transaction.amount_credits
    }

@router.post("/admin/reject-credit-purchase/{transaction_id}")
def reject_credit_purchase(
    transaction_id: int,
    reason: Optional[str] = None,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Rechazar recarga de créditos (ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)

    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")

    if transaction.transaction_type != TransactionType.CREDIT_PURCHASE:
        raise HTTPException(status_code=400, detail="No es una recarga de créditos")

    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="La transacción no está pendiente")

    transaction.status = TransactionStatus.FAILED
    transaction.description = (
        f"{transaction.description} | Rechazada: {reason}"
        if reason else transaction.description
    )

    session.commit()

    return {
        "success": True,
        "message": "Recarga de créditos rechazada",
        "transaction_id": transaction.id
    }

@router.post("/admin/add-credits")
def admin_add_credits(
    request: AdminCreditAdjustmentRequest,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Ajuste manual de créditos por administrador (obsequios/canjes)
    """
    if request.credits <= 0:
        raise HTTPException(status_code=400, detail="La cantidad de créditos debe ser positiva")

    transaction = TransactionService.create_transaction(
        session=session,
        user_id=request.user_id,
        transaction_type=TransactionType.ADMIN_ADJUSTMENT,
        amount_credits=request.credits,
        amount_cop=0,
        reference_type="admin_adjustment",
        description=f"Ajuste manual de {request.credits} créditos"
        + (f" | {request.reason}" if request.reason else "")
    )

    TransactionService.complete_transaction(
        session=session,
        transaction_id=transaction.id,
        update_wallet=True
    )

    session.commit()

    return {
        "success": True,
        "message": "Créditos agregados exitosamente",
        "transaction_id": transaction.id,
        "credits_added": request.credits
    }

@router.get("/admin/history")
def admin_transaction_history(
    status: Optional[str] = None,
    transaction_type: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Historial completo de transacciones (ADMIN)
    """
    query = session.query(Transaction)

    # Filtro por estado
    if status:
        try:
            query = query.filter(
                Transaction.status == TransactionStatus(status)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Estado inválido")

    # Filtro por tipo
    if transaction_type:
        try:
            query = query.filter(
                Transaction.transaction_type == TransactionType(transaction_type)
            )
        except ValueError:
            raise HTTPException(status_code=400, detail="Tipo de transacción inválido")

    total = query.count()

    transactions = (
        query.order_by(Transaction.created_at.desc())
        .offset(offset)
        .limit(limit)
        .all()
    )

    result = []

    for t in transactions:
        result.append({
            "transaction_id": t.id,
            "user_id": t.user_id,
            "wallet_id": t.wallet_id,
            "type": t.transaction_type.value,
            "status": t.status.value,
            "amount_cop": t.amount_cop,
            "amount_credits": t.amount_credits,
            "fee_cop": t.fee_cop,
            "net_amount_cop": t.net_amount_cop,
            "payment_method": t.payment_method,
            "payment_reference": t.payment_reference,
            "reference_id": t.reference_id,
            "reference_type": t.reference_type,
            "description": t.description,
            "created_at": t.created_at,
            "completed_at": t.completed_at,
        })

    return {
        "total": total,
        "limit": limit,
        "offset": offset,
        "transactions": result
    }

@router.get("/admin/dashboard")
def admin_dashboard(
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Resumen global de transacciones y wallets (ADMIN)
    """
    # Totales globales
    total_transactions = session.query(Transaction).count()
    
    total_credits_purchased = (
        session.query(Transaction)
        .filter(Transaction.transaction_type == TransactionType.CREDIT_PURCHASE)
        .with_entities(func.sum(Transaction.amount_credits))
        .scalar() or 0
    )

    total_cop_received = (
        session.query(Transaction)
        .filter(Transaction.transaction_type == TransactionType.CREDIT_PURCHASE)
        .with_entities(func.sum(Transaction.amount_cop))
        .scalar() or 0
    )

    total_prizes_paid = (
        session.query(Transaction)
        .filter(Transaction.transaction_type == TransactionType.PRIZE_WIN)
        .with_entities(func.sum(Transaction.amount_cop))
        .scalar() or 0
    )

    pending_transactions = (
        session.query(Transaction)
        .filter(Transaction.status == TransactionStatus.PENDING)
        .count()
    )

    total_users_with_wallet = session.query(UserWallet).count()
    
    total_credits_in_system = (
        session.query(UserWallet)
        .with_entities(func.sum(UserWallet.credits))
        .scalar() or 0
    )
    
    total_balance_cop = (
        session.query(UserWallet)
        .with_entities(func.sum(UserWallet.balance_cop))
        .scalar() or 0
    )

    current_prize_pool_cop = (
        session.query(func.coalesce(func.sum(BetDate.prize_cop + BetDate.accumulated_prize), 0))
        .scalar() or 0
    )

    admin_adjustment_pending_cop = (
        session.query(func.coalesce(func.sum(func.abs(Transaction.amount_cop)), 0))
        .filter(
            Transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT,
            Transaction.status == TransactionStatus.PENDING,
        )
        .scalar() or 0
    )

    admin_adjustment_completed_cop = (
        session.query(func.coalesce(func.sum(func.abs(Transaction.amount_cop)), 0))
        .filter(
            Transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT,
            Transaction.status == TransactionStatus.COMPLETED,
        )
        .scalar() or 0
    )

    withdrawals_pending_cop = (
        session.query(func.coalesce(func.sum(func.abs(Transaction.amount_cop)), 0))
        .filter(
            Transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT,
            Transaction.status == TransactionStatus.PENDING,
            Transaction.reference_type == "withdrawal",
        )
        .scalar() or 0
    )

    points_to_credits_pending_cop = (
        session.query(func.coalesce(func.sum(func.abs(Transaction.amount_cop)), 0))
        .filter(
            Transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT,
            Transaction.status == TransactionStatus.PENDING,
            Transaction.reference_type == "points_to_credits",
        )
        .scalar() or 0
    )

    return {
        "total_transactions": total_transactions,
        "total_credits_purchased": total_credits_purchased,
        "total_cop_received": total_cop_received,
        "total_prizes_paid": total_prizes_paid,
        "pending_transactions": pending_transactions,
        "total_users_with_wallet": total_users_with_wallet,
        "total_credits_in_system": total_credits_in_system,
        "total_balance_cop": total_balance_cop,
        "current_prize_pool_cop": current_prize_pool_cop,
        "admin_adjustment_pending_cop": admin_adjustment_pending_cop,
        "admin_adjustment_completed_cop": admin_adjustment_completed_cop,
        "withdrawals_pending_cop": withdrawals_pending_cop,
        "points_to_credits_pending_cop": points_to_credits_pending_cop,
    }

@router.get("/admin/pending-transactions", response_model=List[TransactionDetail])
def get_pending_transactions(
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Listar transacciones de recarga de créditos pendientes de aprobación
    """
    pending = session.query(Transaction)\
        .filter(Transaction.transaction_type == TransactionType.CREDIT_PURCHASE)\
        .filter(Transaction.status == TransactionStatus.PENDING)\
        .all()
    
    return [
        TransactionDetail(
            id=t.id,
            transaction_type=t.transaction_type.value,
            status=t.status.value,
            amount_cop=t.amount_cop,
            amount_credits=t.amount_credits,
            fee_cop=t.fee_cop,
            net_amount_cop=t.net_amount_cop,
            description=t.description,
            reference_id=t.reference_id,
            reference_type=t.reference_type,
            created_at=t.created_at,
            completed_at=t.completed_at,
            amount=-t.amount_cop,
            currency="COP",
            credits_affected=t.amount_credits
        )
        for t in pending
    ]


@router.get("/admin/pending-requests")
def get_pending_requests(
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Listar solicitudes pendientes (retiros y canje de puntos a créditos)
    """
    pending = session.query(Transaction)\
        .filter(Transaction.transaction_type == TransactionType.ADMIN_ADJUSTMENT)\
        .filter(Transaction.status == TransactionStatus.PENDING)\
        .order_by(Transaction.created_at.desc())\
        .all()

    return {
        "total": len(pending),
        "requests": [
            {
                "transaction_id": t.id,
                "user_id": t.user_id,
                "user_name": t.user.username if t.user else None,
                "amount_cop": t.amount_cop,
                "amount_credits": t.amount_credits,
                "reference_type": t.reference_type,
                "description": t.description,
                "payment_method": t.payment_method,
                "created_at": t.created_at,
                "status": t.status.value
            }
            for t in pending
        ]
    }


@router.post("/admin/approve-request/{transaction_id}")
def approve_request(
    transaction_id: int,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Aprobar solicitud de retiro o canje de puntos (ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    if transaction.transaction_type != TransactionType.ADMIN_ADJUSTMENT:
        raise HTTPException(status_code=400, detail="La transacción no es una solicitud administrable")
    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="La transacción no está pendiente")

    TransactionService.complete_transaction(session=session, transaction_id=transaction.id, update_wallet=True)
    transaction.description = (transaction.description or "") + f" | Aprobada por admin {admin_user.id}"
    session.commit()

    return {
        "success": True,
        "message": "Solicitud aprobada",
        "transaction_id": transaction.id
    }


@router.post("/admin/reject-request/{transaction_id}")
def reject_request(
    transaction_id: int,
    reason: Optional[str] = None,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)
):
    """
    Rechazar solicitud de retiro o canje de puntos (ADMIN)
    """
    transaction = session.query(Transaction).get(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    if transaction.transaction_type != TransactionType.ADMIN_ADJUSTMENT:
        raise HTTPException(status_code=400, detail="La transacción no es una solicitud administrable")
    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="La transacción no está pendiente")

    transaction.status = TransactionStatus.CANCELLED
    transaction.description = (
        (transaction.description or "")
        + f" | Rechazada por admin {admin_user.id}. Motivo: {reason or 'No especificado'}"
    )
    session.commit()

    return {
        "success": True,
        "message": "Solicitud rechazada",
        "transaction_id": transaction.id
    }

class TransactionApprovalRequest(BaseModel):
    approve: bool = True
    admin_comment: Optional[str] = None

@router.post("/admin/approve-transaction/{transaction_id}")
def approve_transaction(
    transaction_id: int,
    request: TransactionApprovalRequest,
    session: Session = Depends(get_db),
    admin_user: User = Depends(get_current_admin_user)    
):
    """
    Aprobar o rechazar una transacción de recarga de créditos
    """
    transaction = session.query(Transaction).get(transaction_id)
    if not transaction:
        raise HTTPException(status_code=404, detail="Transacción no encontrada")
    
    if transaction.status != TransactionStatus.PENDING:
        raise HTTPException(status_code=400, detail="Transacción ya procesada")
    
    if request.approve:
        # Completar transacción (actualiza wallet)
        TransactionService.complete_transaction(session, transaction_id)
        transaction.description += f" | Aprobada por admin: {request.admin_comment or ''}"
    else:
        transaction.status = TransactionStatus.CANCELLED
        transaction.description += f" | Rechazada por admin: {request.admin_comment or ''}"
        session.commit()
    
    return {"transaction_id": transaction.id, "status": transaction.status.value}
