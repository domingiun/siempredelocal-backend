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
from sqlalchemy.orm import Session

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
        "match_status": m.status if m else None,
    }


def _build_leaderboard(polla: Polla, db: Session) -> list[dict]:
    participants = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla.id)
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

@router.get("/")
def list_pollas(db: Session = Depends(get_db)):
    """Lista todas las pollas (activas y anteriores)."""
    pollas = (
        db.query(Polla)
        .filter(Polla.status != "cancelled")
        .order_by(Polla.edition_year.desc())
        .all()
    )
    return [
        {
            "id": p.id,
            "name": p.name,
            "description": p.description,
            "status": p.status,
            "edition_year": p.edition_year,
            "entry_credits": p.entry_credits,
            "current_prize_cop": p.current_prize_cop,
            "participant_count": len(p.participants),
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
        "participant_count": len(polla.participants),
        "current_prize_cop": polla.current_prize_cop,
        "leaderboard": _build_leaderboard(polla, db),
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
    matches = q.order_by(PollaMatch.phase, PollaMatch.match_order, PollaMatch.id).all()

    return [_polla_match_to_response(pm) for pm in matches]


# ── Endpoints autenticados ─────────────────────────────────────────────────

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
    # Solo los que aún no han cerrado
    open_pending = [
        pm for pm in pending
        if pm.close_at and now < pm.close_at
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
    predictions = q.all()

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

    return {"success": True, "polla_match_id": pm.id, "phase": pm.phase}


@router.delete("/admin/{polla_id}/match/{pm_id}")
def remove_match_from_polla(
    polla_id: int,
    pm_id: int,
    db: Session = Depends(get_db),
    admin: User = Depends(get_current_admin_user),
):
    """Quitar un partido de la polla (solo si no tiene predicciones)."""
    pm = db.get(PollaMatch, pm_id)
    if not pm or pm.polla_id != polla_id:
        raise HTTPException(status_code=404, detail="Partido no encontrado en esta polla")
    if pm.predictions:
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
    return {"success": True, "participant_count": len(polla.participants)}


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
