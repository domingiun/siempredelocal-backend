# backend/app/routes/polla/polla.py
"""
Endpoints de la Polla Mundial 2026.

Públicos (sin auth):
  GET  /polla/                    → listar pollas activas
  GET  /polla/{id}                → detalle + leaderboard
  GET  /polla/{id}/matches        → partidos de la polla

Autenticados:
  POST /polla/{id}/join           → inscribirse (cobra créditos)
  GET  /polla/{id}/me             → mi estado en la polla
  GET  /polla/{id}/my-predictions → mis predicciones
  POST /polla/{id}/predict        → enviar/actualizar predicción

Admin:
  POST /polla/admin/create
  PUT  /polla/admin/{id}
  POST /polla/admin/{id}/add-match
  DELETE /polla/admin/{id}/match/{pm_id}
  POST /polla/admin/{id}/score-match/{pm_id}
  POST /polla/admin/{id}/update-rankings
"""
import logging
from datetime import datetime, timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func
from sqlalchemy.orm import Session, selectinload

from app.db import get_db
from app.core.security import get_current_user
from app.core.dependencies import get_current_admin_user
from app.models.user.user import User
from app.models.polla.polla import (
    Polla, PollaMatch, PollaParticipant, PollaPrediction,
    PollaPhase, PHASE_POINTS,
)
from app.models.bet.UserWallet import UserWallet
from app.models.bet.transaction import Transaction, TransactionType, TransactionStatus
from app.models.competition.match import Match
from app.models.competition.team import Team
from app.schemas.polla.polla import (
    PollaCreate, PollaUpdate, PollaMatchCreate, PollaMatchScore,
    PollaPredictionSubmit, PollaResponse, PollaMatchResponse,
    PollaPredictionResponse, LeaderboardEntry, MyPollaStatus,
)
from app.services.polla_scoring_service import (
    score_polla_match, _update_rankings,
    compute_polla_result_from_match,
)

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/polla", tags=["Polla Mundial"])


# ── Helpers ────────────────────────────────────────────────────────────────

def _polla_match_to_response(pm: PollaMatch) -> dict:
    m = pm.match
    home_team = m.home_team if m else None
    away_team = m.away_team if m else None
    return {
        "id": pm.id,
        "polla_id": pm.polla_id,
        "match_id": pm.match_id,
        "phase": pm.phase,
        "match_order": pm.match_order,
        "actual_result": pm.actual_result,
        "actual_winner_id": pm.actual_winner_id,
        "actual_winner_name": pm.actual_winner.name if pm.actual_winner else None,
        "is_scored": pm.is_scored,
        "close_at": pm.close_at,
        "match_date": m.match_date if m else None,
        "home_team": home_team.name if home_team else None,
        "away_team": away_team.name if away_team else None,
        "home_team_id": home_team.id if home_team else None,
        "away_team_id": away_team.id if away_team else None,
        "home_logo": home_team.logo_url if home_team else None,
        "away_logo": away_team.logo_url if away_team else None,
        "home_score": m.home_score if m else None,
        "away_score": m.away_score if m else None,
        "penalty_home": m.penalty_home if m else None,
        "penalty_away": m.penalty_away if m else None,
        "match_status": m.status if m else None,
    }


def _build_leaderboard(polla: Polla, db: Session) -> list[dict]:
    participants = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla.id)
        .options(selectinload(PollaParticipant.user))
        .order_by(PollaParticipant.total_points.desc(), PollaParticipant.joined_at)
        .all()
    )
    result = []
    rank = 1
    prev_pts = None
    for i, p in enumerate(participants):
        if p.total_points != prev_pts:
            rank = i + 1
        prev_pts = p.total_points
        result.append({
            "rank": rank,
            "user_id": p.user_id,
            "username": p.user.username if p.user else f"Usuario {p.user_id}",
            "avatar_url": p.user.avatar_url if p.user else None,
            "base_points": p.base_points,
            "bonus_points": p.bonus_points,
            "total_points": p.total_points,
            "prize_won_cop": p.prize_won_cop,
        })
    return result


# ── Endpoints públicos ─────────────────────────────────────────────────────

def _participant_counts(polla_ids: list[int], db: Session) -> dict[int, int]:
    """Una sola query COUNT agrupada — evita N lazy loads de p.participants."""
    if not polla_ids:
        return {}
    rows = (
        db.query(PollaParticipant.polla_id, func.count(PollaParticipant.id))
        .filter(PollaParticipant.polla_id.in_(polla_ids))
        .group_by(PollaParticipant.polla_id)
        .all()
    )
    return {pid: cnt for pid, cnt in rows}


@router.get("/admin/all")
def admin_list_all_pollas(
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Lista TODAS las pollas incluyendo ocultas y canceladas (solo admin)."""
    pollas = db.query(Polla).order_by(Polla.edition_year.desc()).all()
    counts = _participant_counts([p.id for p in pollas], db)
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "edition_year": p.edition_year,
            "entry_credits": p.entry_credits,
            "current_prize_cop": p.current_prize_cop,
            "participant_count": counts.get(p.id, 0),
            "registration_open_at": p.registration_open_at,
            "registration_close_at": p.registration_close_at,
        }
        for p in pollas
    ]


@router.get("/")
def list_pollas(db: Session = Depends(get_db)):
    """Lista pollas visibles al público (excluye hidden y cancelled)."""
    pollas = (
        db.query(Polla)
        .filter(Polla.status.notin_(["cancelled", "hidden"]))
        .order_by(Polla.edition_year.desc())
        .all()
    )
    counts = _participant_counts([p.id for p in pollas], db)
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "edition_year": p.edition_year,
            "entry_credits": p.entry_credits,
            "current_prize_cop": p.current_prize_cop,
            "participant_count": counts.get(p.id, 0),
            "registration_open_at": p.registration_open_at,
            "registration_close_at": p.registration_close_at,
        }
        for p in pollas
    ]


@router.get("/{polla_id}")
def get_polla(polla_id: int, db: Session = Depends(get_db)):
    """Detalle de la polla con leaderboard."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    return {
        "id": polla.id,
        "name": polla.name,
        "description": polla.description,
        "status": polla.status,
        "edition_year": polla.edition_year,
        "entry_credits": polla.entry_credits,
        "guaranteed_prize_cop": polla.guaranteed_prize_cop,
        "prize_per_user_cop": polla.prize_per_user_cop,
        "threshold_users": polla.threshold_users,
        "platform_fee_pct": polla.platform_fee_pct,
        "registration_open_at": polla.registration_open_at,
        "registration_close_at": polla.registration_close_at,
        "created_at": polla.created_at,
        "current_prize_cop": polla.current_prize_cop,
        "leaderboard": (leaderboard := _build_leaderboard(polla, db)),
        "participant_count": len(leaderboard),
    }


@router.get("/{polla_id}/matches")
def get_polla_matches(
    polla_id: int,
    phase: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Partidos de la polla, opcionalmente filtrado por fase."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    q = db.query(PollaMatch).filter(PollaMatch.polla_id == polla_id)
    if phase:
        q = q.filter(PollaMatch.phase == phase)
    matches = (
        q.options(
            selectinload(PollaMatch.match).options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
            ),
            selectinload(PollaMatch.actual_winner),
        )
        .order_by(PollaMatch.phase, PollaMatch.match_order, PollaMatch.id)
        .all()
    )

    return [_polla_match_to_response(pm) for pm in matches]


# ── Endpoints autenticados ─────────────────────────────────────────────────

@router.post("/{polla_id}/purchase-entry")
def purchase_polla_entry(
    polla_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Registra una transacción pendiente de recarga para inscribirse en la polla.
    El admin aprueba el pago → créditos acreditados → usuario puede inscribirse.
    """
    from app.services.transaction_service import TransactionService

    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")
    if polla.status not in ("open", "in_progress"):
        raise HTTPException(status_code=400, detail="La polla no está abierta para inscripciones")

    existing = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya estás inscrito en esta polla")

    amount_cop = polla.entry_credits * 5_000  # $5,000 COP por crédito

    tx = TransactionService.create_transaction(
        session=db,
        user_id=current_user.id,
        transaction_type=TransactionType.CREDIT_PURCHASE,
        amount_cop=amount_cop,
        amount_credits=polla.entry_credits,
        description=f"Recarga para inscripción en {polla.name}",
        payment_method="nequi",
    )
    db.commit()
    db.refresh(tx)

    logger.info(
        f"[polla] Usuario {current_user.id} solicitó recarga de entrada "
        f"para polla {polla_id} — tx {tx.id} por ${amount_cop:,} COP"
    )

    return {
        "transaction_id": tx.id,
        "amount_cop": amount_cop,
        "credits": polla.entry_credits,
        "polla_name": polla.name,
    }


@router.post("/{polla_id}/join")
def join_polla(
    polla_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Inscribirse en la polla. Descuenta entry_credits de la wallet del usuario.
    """
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")
    if polla.status not in ("open", "in_progress"):
        raise HTTPException(
            status_code=400,
            detail=f"La polla no está abierta para inscripciones (estado: {polla.status})"
        )

    # Verificar si ya está inscrito
    existing = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .first()
    )
    if existing:
        raise HTTPException(status_code=400, detail="Ya estás inscrito en esta polla")

    # Verificar y descontar créditos (SELECT FOR UPDATE para evitar race condition)
    wallet = (
        db.query(UserWallet)
        .filter_by(user_id=current_user.id)
        .with_for_update()
        .first()
    )
    if not wallet or wallet.credits < polla.entry_credits:
        have = wallet.credits if wallet else 0
        raise HTTPException(
            status_code=400,
            detail=f"Créditos insuficientes. Necesitas {polla.entry_credits}, tienes {have}"
        )

    wallet.credits -= polla.entry_credits

    # Registrar transacción
    tx = Transaction(
        user_id=current_user.id,
        wallet_id=wallet.id,
        transaction_type=TransactionType.BET_PLACEMENT,
        amount_credits=polla.entry_credits,
        amount_cop=polla.entry_credits * 5_000,
        status=TransactionStatus.COMPLETED,
        description=f"Inscripción {polla.name}",
    )
    db.add(tx)

    # Crear participante
    participant = PollaParticipant(
        polla_id=polla_id,
        user_id=current_user.id,
    )
    db.add(participant)
    db.commit()
    db.refresh(participant)

    logger.info(
        f"[polla] Usuario {current_user.id} inscrito en polla {polla_id} "
        f"(credits descontados: {polla.entry_credits})"
    )

    return {
        "success": True,
        "message": f"Inscrito exitosamente en {polla.name}",
        "participant_id": participant.id,
        "credits_remaining": wallet.credits,
        "current_prize_cop": polla.current_prize_cop,
    }


@router.get("/{polla_id}/me")
def get_my_polla_status(
    polla_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Estado del usuario actual en la polla."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    participant = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .options(selectinload(PollaParticipant.predictions))
        .first()
    )

    if not participant:
        return {
            "is_participant": False,
            "participant_id": None,
            "rank": None,
            "base_points": 0,
            "bonus_points": 0,
            "total_points": 0,
            "predictions_submitted": 0,
            "predictions_pending": 0,
        }

    submitted_ids = {pred.polla_match_id for pred in participant.predictions}
    now = datetime.utcnow()

    # Partidos aún abiertos para predicción donde no ha predicho
    pending = (
        db.query(PollaMatch)
        .filter(
            PollaMatch.polla_id == polla_id,
            PollaMatch.is_scored == False,
            PollaMatch.id.notin_(submitted_ids),
        )
        .all()
    )
    # Solo los que aún no han cerrado (None = sin cierre = abierto)
    open_pending = [
        pm for pm in pending
        if pm.close_at is None or now < pm.close_at
    ]

    return {
        "is_participant": True,
        "participant_id": participant.id,
        "rank": participant.rank,
        "base_points": participant.base_points,
        "bonus_points": participant.bonus_points,
        "total_points": participant.total_points,
        "predictions_submitted": len(submitted_ids),
        "predictions_pending": len(open_pending),
    }


@router.get("/{polla_id}/my-predictions")
def get_my_predictions(
    polla_id: int,
    phase: Optional[str] = None,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """Mis predicciones en la polla."""
    participant = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .first()
    )
    if not participant:
        raise HTTPException(status_code=404, detail="No estás inscrito en esta polla")

    q = db.query(PollaPrediction).filter_by(participant_id=participant.id)
    if phase:
        q = q.join(PollaMatch).filter(PollaMatch.phase == phase)
    predictions = q.options(
        selectinload(PollaPrediction.polla_match).options(
            selectinload(PollaMatch.match).options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
            ),
            selectinload(PollaMatch.actual_winner),
        ),
        selectinload(PollaPrediction.predicted_winner),
    ).all()

    return [
        {
            "id": pred.id,
            "polla_match_id": pred.polla_match_id,
            "phase": pred.polla_match.phase,
            "prediction_result": pred.prediction_result,
            "predicted_winner_id": pred.predicted_winner_id,
            "predicted_winner_name": (
                pred.predicted_winner.name if pred.predicted_winner else None
            ),
            "points": pred.points,
            "is_correct": pred.is_correct,
            "submitted_at": pred.submitted_at,
            "match": _polla_match_to_response(pred.polla_match),
        }
        for pred in predictions
    ]


@router.get("/{polla_id}/participant/{user_id}/predictions")
def get_participant_scored_predictions(
    polla_id: int,
    user_id: int,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Predicciones de otro participante, SOLO para partidos ya puntuados.
    Accesible para cualquier participante inscrito en la misma polla.
    """
    # Verificar que quien consulta también está inscrito
    my_participant = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .first()
    )
    if not my_participant:
        raise HTTPException(status_code=403, detail="No estás inscrito en esta polla")

    # Buscar el participante objetivo
    participant = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=user_id)
        .options(selectinload(PollaParticipant.user))
        .first()
    )
    if not participant:
        raise HTTPException(status_code=404, detail="Participante no encontrado")

    # Solo predicciones de partidos ya puntuados
    predictions = (
        db.query(PollaPrediction)
        .join(PollaMatch)
        .filter(
            PollaPrediction.participant_id == participant.id,
            PollaMatch.is_scored == True,
        )
        .options(
            selectinload(PollaPrediction.polla_match).options(
                selectinload(PollaMatch.match).options(
                    selectinload(Match.home_team),
                    selectinload(Match.away_team),
                ),
                selectinload(PollaMatch.actual_winner),
            ),
            selectinload(PollaPrediction.predicted_winner),
        )
        .order_by(PollaMatch.match_order, PollaMatch.id)
        .all()
    )

    return {
        "user_id": user_id,
        "username": participant.user.username,
        "rank": participant.rank,
        "total_points": participant.total_points,
        "predictions": [
            {
                "id": pred.id,
                "phase": pred.polla_match.phase,
                "prediction_result": pred.prediction_result,
                "predicted_winner_name": (
                    pred.predicted_winner.name if pred.predicted_winner else None
                ),
                "points": pred.points,
                "is_correct": pred.is_correct,
                "match": _polla_match_to_response(pred.polla_match),
            }
            for pred in predictions
        ],
    }


@router.get("/{polla_id}/next-matches")
def get_next_matches_to_predict(
    polla_id: int,
    limit: int = 10,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Todos los partidos abiertos para predecir o editar (no cerrados, no puntuados).
    Incluye partidos con predicción existente para permitir edición hasta 1h antes.
    """
    participant = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .first()
    )
    if not participant:
        raise HTTPException(status_code=403, detail="No estás inscrito en esta polla")

    now = datetime.utcnow()

    open_matches = (
        db.query(PollaMatch)
        .filter(
            PollaMatch.polla_id == polla_id,
            PollaMatch.is_scored == False,
        )
        .options(
            selectinload(PollaMatch.match).options(
                selectinload(Match.home_team),
                selectinload(Match.away_team),
            ),
            selectinload(PollaMatch.actual_winner),
        )
        .all()
    )

    # Solo los que aún no han cerrado
    available = [
        pm for pm in open_matches
        if pm.close_at is None or now < pm.close_at
    ]
    available.sort(key=lambda pm: pm.close_at or datetime.max)

    return [_polla_match_to_response(pm) for pm in available[:limit]]


@router.post("/{polla_id}/predict")
def submit_prediction(
    polla_id: int,
    body: PollaPredictionSubmit,
    db: Session = Depends(get_db),
    current_user: User = Depends(get_current_user),
):
    """
    Enviar o actualizar una predicción para un partido de la polla.
    Grupos: prediction_result = "L"/"E"/"V".
    Eliminatorias: predicted_winner_id = ID del equipo ganador esperado.
    """
    participant = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id, user_id=current_user.id)
        .first()
    )
    if not participant:
        raise HTTPException(status_code=403, detail="No estás inscrito en esta polla")

    polla_match = db.get(PollaMatch, body.polla_match_id)
    if not polla_match or polla_match.polla_id != polla_id:
        raise HTTPException(status_code=404, detail="Partido no encontrado en esta polla")
    if polla_match.is_scored:
        raise HTTPException(status_code=400, detail="Este partido ya fue puntuado")

    now = datetime.utcnow()
    if polla_match.close_at and now >= polla_match.close_at:
        raise HTTPException(
            status_code=400,
            detail="Las predicciones para este partido ya cerraron"
        )

    is_groups = polla_match.phase == "groups"
    if is_groups:
        if body.prediction_result not in ("L", "E", "V"):
            raise HTTPException(
                status_code=400,
                detail="Para la fase de grupos, prediction_result debe ser 'L', 'E' o 'V'"
            )
    else:
        if not body.predicted_winner_id:
            raise HTTPException(
                status_code=400,
                detail="Para eliminatorias, debes indicar predicted_winner_id"
            )
        team = db.get(Team, body.predicted_winner_id)
        if not team:
            raise HTTPException(status_code=404, detail="Equipo no encontrado")

    # Crear o actualizar predicción
    existing = (
        db.query(PollaPrediction)
        .filter_by(participant_id=participant.id, polla_match_id=body.polla_match_id)
        .first()
    )
    if existing:
        existing.prediction_result = body.prediction_result
        existing.predicted_winner_id = body.predicted_winner_id
        existing.updated_at = now
        pred = existing
    else:
        pred = PollaPrediction(
            participant_id=participant.id,
            polla_match_id=body.polla_match_id,
            prediction_result=body.prediction_result,
            predicted_winner_id=body.predicted_winner_id,
        )
        db.add(pred)

    db.commit()
    db.refresh(pred)

    return {
        "success": True,
        "prediction_id": pred.id,
        "polla_match_id": pred.polla_match_id,
        "prediction_result": pred.prediction_result,
        "predicted_winner_id": pred.predicted_winner_id,
    }


# ── Endpoints Admin ────────────────────────────────────────────────────────

@router.post("/admin/create")
def create_polla(
    body: PollaCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Crear una nueva polla."""
    polla = Polla(**body.model_dump())
    db.add(polla)
    db.commit()
    db.refresh(polla)
    logger.info(f"[polla] Polla {polla.id} creada por admin {admin.id}")
    return {"id": polla.id, "name": polla.name, "status": polla.status}


@router.put("/admin/{polla_id}")
def update_polla(
    polla_id: int,
    body: PollaUpdate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Editar una polla (nombre, estado, parámetros económicos)."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    for field, value in body.model_dump(exclude_none=True).items():
        setattr(polla, field, value)

    db.commit()
    return {"success": True, "id": polla.id, "status": polla.status}


@router.post("/admin/{polla_id}/add-match")
def add_match_to_polla(
    polla_id: int,
    body: PollaMatchCreate,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Agregar un partido existente a la polla con su fase."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    match = db.get(Match, body.match_id)
    if not match:
        raise HTTPException(status_code=404, detail="Partido no encontrado")

    # Verificar que no esté ya en la polla
    exists = (
        db.query(PollaMatch)
        .filter_by(polla_id=polla_id, match_id=body.match_id)
        .first()
    )
    if exists:
        raise HTTPException(status_code=400, detail="Este partido ya está en la polla")

    # close_at = 1 hora antes del partido
    close_at = (match.match_date - timedelta(hours=1)) if match.match_date else None

    pm = PollaMatch(
        polla_id=polla_id,
        match_id=body.match_id,
        phase=body.phase,
        match_order=body.match_order,
        close_at=close_at,
    )
    db.add(pm)
    db.commit()
    db.refresh(pm)

    # Si el partido ya estaba Finalizado cuando se agregó, puntuar inmediatamente
    if match.status == "Finalizado" and match.home_score is not None and match.away_score is not None:
        try:
            from app.services.polla_scoring_service import auto_score_polla_matches_for_match
            auto_score_polla_matches_for_match(match.id, db)
            logger.info(f"[polla] Partido {match.id} ya finalizado — scored al agregar a polla {polla_id}")
        except Exception as e:
            logger.error(f"[polla] Error al scoring inmediato de partido {match.id}: {e}")

    return {"success": True, "polla_match_id": pm.id, "phase": pm.phase}


@router.delete("/admin/{polla_id}/match/{pm_id}")
def remove_match_from_polla(
    polla_id: int,
    pm_id: int,
    force: bool = False,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Quitar un partido de la polla (solo si no tiene predicciones, salvo force=true)."""
    pm = db.get(PollaMatch, pm_id)
    if not pm or pm.polla_id != polla_id:
        raise HTTPException(status_code=404, detail="Partido no encontrado en esta polla")
    if pm.predictions and not force:
        raise HTTPException(
            status_code=400,
            detail="No se puede eliminar un partido que ya tiene predicciones"
        )
    db.delete(pm)
    db.commit()
    return {"success": True}


@router.post("/admin/{polla_id}/score-match/{pm_id}")
def admin_score_match(
    polla_id: int,
    pm_id: int,
    body: PollaMatchScore,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Puntuar manualmente un partido de la polla."""
    pm = db.get(PollaMatch, pm_id)
    if not pm or pm.polla_id != polla_id:
        raise HTTPException(status_code=404, detail="Partido no encontrado en esta polla")

    if body.actual_result:
        pm.actual_result = body.actual_result
    if body.actual_winner_id:
        pm.actual_winner_id = body.actual_winner_id

    db.commit()
    score_polla_match(pm_id, db)

    return {"success": True, "polla_match_id": pm_id}


@router.post("/admin/{polla_id}/update-rankings")
def admin_update_rankings(
    polla_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Recalcular rankings de la polla manualmente."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    _update_rankings(polla_id, db)
    db.commit()
    count = db.query(func.count(PollaParticipant.id)).filter_by(polla_id=polla_id).scalar()
    return {"success": True, "participant_count": count}


@router.post("/admin/{polla_id}/reset-close-at")
def reset_close_at(
    polla_id: int,
    hours: int = 2,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Mueve close_at de todos los partidos no puntuados a (now + hours).
    Útil para habilitar predicciones en una polla de prueba con partidos ya vencidos.
    """
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    new_close = datetime.utcnow() + timedelta(hours=hours)
    matches = (
        db.query(PollaMatch)
        .filter(PollaMatch.polla_id == polla_id, PollaMatch.is_scored == False)
        .all()
    )
    for pm in matches:
        pm.close_at = new_close
    db.commit()
    logger.info(f"[polla] reset close_at → {new_close} en {len(matches)} partidos de polla {polla_id}")
    return {"success": True, "updated": len(matches), "new_close_at": new_close.isoformat()}


@router.get("/admin/{polla_id}/participants")
def admin_list_participants(
    polla_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Lista de participantes con puntos (vista admin)."""
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    return _build_leaderboard(polla, db)


@router.post("/admin/{polla_id}/finalize")
def admin_finalize_polla(
    polla_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Finaliza la polla: identifica al(los) ganador(es) por mayor total_points,
    divide el premio entre empatados, acredita saldo COP en sus wallets y
    marca la polla como 'finished'. Idempotente respecto al doble pago.
    """
    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")
    if polla.status == "finished":
        raise HTTPException(status_code=400, detail="La polla ya fue finalizada y liquidada")

    unscored = (
        db.query(PollaMatch)
        .filter(PollaMatch.polla_id == polla_id, PollaMatch.is_scored == False)
        .count()
    )
    if unscored > 0:
        raise HTTPException(
            status_code=400,
            detail=f"Hay {unscored} partido(s) sin puntuar. Usa 'Puntuar partidos finalizados' primero."
        )

    participants = db.query(PollaParticipant).filter_by(polla_id=polla_id).all()
    if not participants:
        raise HTTPException(status_code=400, detail="No hay participantes en esta polla")

    max_pts = max(p.total_points for p in participants)
    winners = [p for p in participants if p.total_points == max_pts]

    total_prize = polla.current_prize_cop
    fee_pct = polla.platform_fee_pct or 0
    net_total = int(total_prize * (1 - fee_pct / 100))
    prize_per_winner = net_total // len(winners)

    winner_details = []
    for participant in winners:
        if participant.prize_distributed:
            winner_details.append({
                "user_id": participant.user_id,
                "username": participant.user.username if participant.user else str(participant.user_id),
                "total_points": participant.total_points,
                "prize_cop": participant.prize_won_cop,
                "already_distributed": True,
            })
            continue

        wallet = (
            db.query(UserWallet)
            .filter_by(user_id=participant.user_id)
            .with_for_update()
            .first()
        )
        if not wallet:
            wallet = UserWallet(user_id=participant.user_id, credits=0, balance_cop=0, total_prizes_won=0)
            db.add(wallet)
            db.flush()

        wallet.balance_cop += prize_per_winner
        wallet.total_prizes_won = (wallet.total_prizes_won or 0) + prize_per_winner

        tx = Transaction(
            user_id=participant.user_id,
            wallet_id=wallet.id,
            transaction_type=TransactionType.PRIZE_WIN,
            amount_cop=prize_per_winner,
            net_amount_cop=prize_per_winner,
            status=TransactionStatus.COMPLETED,
            description=f"Premio {polla.name} — {max_pts} pts · {len(winners)} ganador(es)",
        )
        db.add(tx)

        participant.prize_won_cop = prize_per_winner
        participant.prize_distributed = True

        winner_details.append({
            "user_id": participant.user_id,
            "username": participant.user.username if participant.user else str(participant.user_id),
            "total_points": participant.total_points,
            "prize_cop": prize_per_winner,
            "already_distributed": False,
        })

    polla.status = "finished"
    db.commit()

    logger.info(
        f"[polla] Polla {polla_id} finalizada por admin {admin.id}. "
        f"Ganadores: {[w['username'] for w in winner_details]} · "
        f"Premio neto/ganador: ${prize_per_winner:,} COP"
    )

    return {
        "success": True,
        "winners": winner_details,
        "total_prize_cop": total_prize,
        "fee_pct": fee_pct,
        "net_total_cop": net_total,
        "prize_per_winner_cop": prize_per_winner,
        "winner_count": len(winners),
    }


@router.post("/admin/{polla_id}/rescore-match/{pm_id}")
def admin_rescore_match(
    polla_id: int,
    pm_id: int,
    body: PollaMatchScore,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Corrige el resultado de un PollaMatch ya puntuado y recalcula TODOS los
    puntos de la polla desde cero. Usar cuando se ingresó un marcador incorrecto.

    - Si body.actual_result / actual_winner_id se envía, usa ese valor.
    - Si no se envía, re-deriva el resultado desde el marcador actual del partido.
    """
    from app.models.polla.polla import PHASE_ORDER

    pm = db.get(PollaMatch, pm_id)
    if not pm or pm.polla_id != polla_id:
        raise HTTPException(status_code=404, detail="Partido no encontrado en esta polla")
    if not pm.is_scored:
        raise HTTPException(
            status_code=400,
            detail="Este partido no ha sido puntuado — usa score-match"
        )

    is_groups = (pm.phase == "groups")

    # Actualizar resultado: manual override o re-derivar del partido real
    if body.actual_result is not None:
        pm.actual_result = body.actual_result
        pm.actual_winner_id = None
    elif body.actual_winner_id is not None:
        pm.actual_winner_id = body.actual_winner_id
        pm.actual_result = None
    else:
        if not pm.match_id:
            raise HTTPException(
                status_code=400,
                detail="Sin partido vinculado — provee actual_result manualmente"
            )
        match = db.get(Match, pm.match_id)
        if not match or match.home_score is None or match.away_score is None:
            raise HTTPException(
                status_code=400,
                detail="El partido no tiene marcador — provee actual_result manualmente"
            )
        derived_result, derived_winner = compute_polla_result_from_match(match, is_groups)
        pm.actual_result = derived_result
        pm.actual_winner_id = derived_winner

    # Todos los partidos ya puntuados, ordenados por fase y match_order
    all_scored = (
        db.query(PollaMatch)
        .filter(PollaMatch.polla_id == polla_id, PollaMatch.is_scored == True)
        .all()
    )

    def _phase_key(m):
        try:
            return (PHASE_ORDER.index(m.phase), m.match_order, m.id)
        except ValueError:
            return (99, m.match_order, m.id)

    all_scored.sort(key=_phase_key)
    scored_ids = [m.id for m in all_scored]

    # Reset completo de participantes
    participants = db.query(PollaParticipant).filter_by(polla_id=polla_id).all()
    for p in participants:
        p.base_points = 0
        p.bonus_points = 0
        p.total_points = 0

    # Reset completo de predicciones e is_scored
    for m in all_scored:
        for pred in m.predictions:
            pred.points = 0
            pred.is_correct = False
        m.is_scored = False

    db.commit()

    # Replay: re-puntuar cada partido en orden de fase
    for mid in scored_ids:
        score_polla_match(mid, db)

    _update_rankings(polla_id, db)
    db.commit()

    logger.info(
        f"[polla] rescore-match polla {polla_id}: corregido pm {pm_id} "
        f"→ result={pm.actual_result} winner={pm.actual_winner_id}, "
        f"replay de {len(scored_ids)} partidos"
    )
    return {
        "success": True,
        "rescored_matches": len(scored_ids),
        "corrected_pm_id": pm_id,
        "new_actual_result": pm.actual_result,
        "new_actual_winner_id": pm.actual_winner_id,
    }


@router.post("/admin/{polla_id}/rescore-finished")
def admin_rescore_finished(
    polla_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Puntúa automáticamente todos los PollaMatches sin puntuar cuyo partido
    real ya está Finalizado. Útil cuando el scheduler no pudo ejecutar
    auto_score (p.ej. partidos cargados después de que terminaron).
    """
    from app.services.polla_scoring_service import auto_score_polla_matches_for_match

    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    unscored_pms = (
        db.query(PollaMatch)
        .filter(PollaMatch.polla_id == polla_id, PollaMatch.is_scored == False)
        .all()
    )

    scored_count = 0
    skipped_count = 0
    for pm in unscored_pms:
        if not pm.match_id:
            skipped_count += 1
            continue
        match = db.get(Match, pm.match_id)
        if (not match
                or match.status != "Finalizado"
                or match.home_score is None
                or match.away_score is None):
            skipped_count += 1
            continue
        auto_score_polla_matches_for_match(pm.match_id, db)
        scored_count += 1

    _update_rankings(polla_id, db)
    db.commit()

    logger.info(
        f"[polla] rescore-finished polla {polla_id}: "
        f"puntuados={scored_count} omitidos={skipped_count}"
    )
    return {"success": True, "scored": scored_count, "skipped": skipped_count}


@router.post("/admin/{polla_id}/recompute-bonuses")
def admin_recompute_bonuses(
    polla_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """
    Resetea bonus_points a 0 y recalcula los bonos de TODAS las fases
    que ya tienen todos sus partidos puntuados. Usar cuando cambió la lógica
    de bonificaciones o para corregir bonos mal aplicados.
    """
    from app.services.polla_scoring_service import (
        _compute_racha_bonus, _compute_most_correct_bonus,
    )
    from app.models.polla.polla import PHASE_ORDER

    polla = db.get(Polla, polla_id)
    if not polla:
        raise HTTPException(status_code=404, detail="Polla no encontrada")

    # Reset bonos de todos los participantes
    participants = db.query(PollaParticipant).filter_by(polla_id=polla_id).all()
    for p in participants:
        p.bonus_points = 0

    db.flush()

    # Recalcular bonos por cada fase completamente puntuada
    phases_done = []
    for phase in PHASE_ORDER:
        total = (
            db.query(PollaMatch)
            .filter(PollaMatch.polla_id == polla_id, PollaMatch.phase == phase)
            .count()
        )
        if total == 0:
            continue
        unscored = (
            db.query(PollaMatch)
            .filter(
                PollaMatch.polla_id == polla_id,
                PollaMatch.phase == phase,
                PollaMatch.is_scored == False,
            )
            .count()
        )
        if unscored > 0:
            continue
        _compute_racha_bonus(polla_id, phase, db)
        _compute_most_correct_bonus(polla_id, phase, db)
        phases_done.append(phase)

    # Recalcular total_points
    for p in participants:
        p.total_points = p.base_points + p.bonus_points

    _update_rankings(polla_id, db)
    db.commit()

    logger.info(f"[polla] recompute-bonuses polla {polla_id}: fases={phases_done}")
    return {"success": True, "phases_recomputed": phases_done}
