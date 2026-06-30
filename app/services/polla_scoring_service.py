# backend/app/services/polla_scoring_service.py
"""
Lógica de puntuación para la Polla Mundial.

Puntos base por fase:
  - groups: 1 pt por L/E/V correcto
  - r32, r16: 2 pts por ganador correcto
  - qf, sf, third, final: 3 pts por ganador correcto

Bonificaciones (calculadas al finalizar cada fase):
  1. Racha: cada bloque de 3 consecutivos correctos en la misma racha = +1 pt.
     Racha de 3-5=+1, 6-8=+2, 9-11=+3, etc. Múltiples rachas se acumulan.
  2. Más aciertos: el/los participantes con más correctos en la fase reciben
     +5 (groups, r32) o +3 (r16 en adelante).
"""
import logging
from sqlalchemy.orm import Session

from app.models.polla.polla import (
    Polla, PollaMatch, PollaParticipant, PollaPrediction,
    PHASE_POINTS, PHASE_BONUS_MOST_CORRECT, PHASE_ORDER,
)

logger = logging.getLogger(__name__)


def score_polla_match(polla_match_id: int, db: Session) -> None:
    """
    Puntúa todas las predicciones del partido dado y actualiza puntos base
    de cada participante. Llama a _maybe_compute_phase_bonuses al final.
    """
    polla_match: PollaMatch | None = db.get(PollaMatch, polla_match_id)
    if not polla_match:
        logger.warning(f"[polla] PollaMatch {polla_match_id} no encontrado")
        return
    if polla_match.is_scored:
        logger.debug(f"[polla] PollaMatch {polla_match_id} ya puntuado — skip")
        return

    phase = polla_match.phase
    pts = PHASE_POINTS.get(phase, 1)
    is_groups = (phase == "groups")

    # Verificar que el partido tenga resultado
    if is_groups:
        if polla_match.actual_result is None:
            logger.warning(f"[polla] PollaMatch {polla_match_id} sin actual_result — skip")
            return
        correct_result = polla_match.actual_result
    else:
        if polla_match.actual_winner_id is None:
            logger.warning(f"[polla] PollaMatch {polla_match_id} sin actual_winner_id — skip")
            return
        correct_winner_id = polla_match.actual_winner_id

    predictions: list[PollaPrediction] = (
        db.query(PollaPrediction)
        .filter(PollaPrediction.polla_match_id == polla_match_id)
        .all()
    )

    for pred in predictions:
        if is_groups:
            pred.is_correct = pred.prediction_result == correct_result
        else:
            pred.is_correct = pred.predicted_winner_id == correct_winner_id

        pred.points = pts if pred.is_correct else 0

        participant = pred.participant
        if participant:
            participant.base_points += pred.points
            participant.total_points = participant.base_points + participant.bonus_points

    polla_match.is_scored = True
    db.commit()

    logger.info(
        f"[polla] PollaMatch {polla_match_id} puntuado — "
        f"{sum(1 for p in predictions if p.is_correct)}/{len(predictions)} aciertos"
    )

    _maybe_compute_phase_bonuses(polla_match.polla_id, phase, db)


def _maybe_compute_phase_bonuses(polla_id: int, phase: str, db: Session) -> None:
    """Si todos los partidos de la fase están puntuados, calcula las bonificaciones."""
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
        return

    logger.info(f"[polla] Fase {phase} de polla {polla_id} completada — calculando bonificaciones")

    _compute_racha_bonus(polla_id, phase, db)
    _compute_most_correct_bonus(polla_id, phase, db)

    # Recalcular total_points para todos los participantes
    participants = db.query(PollaParticipant).filter_by(polla_id=polla_id).all()
    for p in participants:
        p.total_points = p.base_points + p.bonus_points

    db.commit()

    # Si era la última fase, actualizar rankings y distribución de premios
    _maybe_finalize_polla(polla_id, phase, db)


def _compute_racha_bonus(polla_id: int, phase: str, db: Session) -> None:
    """
    +1 pt por cada bloque de 3 predicciones consecutivas correctas en la misma racha.
    Racha de 3-5 = +1, de 6-8 = +2, de 9-11 = +3, etc. (floor(racha/3))
    Múltiples rachas separadas se suman independientemente.
    """
    phase_matches = (
        db.query(PollaMatch)
        .filter(PollaMatch.polla_id == polla_id, PollaMatch.phase == phase)
        .order_by(PollaMatch.match_order, PollaMatch.id)
        .all()
    )
    phase_match_ids = {pm.id for pm in phase_matches}

    participants = db.query(PollaParticipant).filter_by(polla_id=polla_id).all()
    for participant in participants:
        pred_by_match = {
            pred.polla_match_id: pred
            for pred in participant.predictions
            if pred.polla_match_id in phase_match_ids
        }

        streak = 0
        total_bonus = 0
        for pm in phase_matches:
            pred = pred_by_match.get(pm.id)
            if pred and pred.is_correct:
                streak += 1
            else:
                total_bonus += streak // 3
                streak = 0
        # Racha abierta al final de la fase también cuenta
        total_bonus += streak // 3

        if total_bonus > 0:
            participant.bonus_points += total_bonus
            logger.info(
                f"[polla] Racha +{total_bonus} → participant {participant.id} "
                f"(user {participant.user_id}) en fase {phase}"
            )


def _compute_most_correct_bonus(polla_id: int, phase: str, db: Session) -> None:
    """
    El/los participantes con más aciertos en la fase reciben +5 (groups, r32)
    o +3 (r16 en adelante).
    """
    bonus = PHASE_BONUS_MOST_CORRECT.get(phase, 3)

    phase_match_ids = {
        pm.id for pm in
        db.query(PollaMatch)
        .filter(PollaMatch.polla_id == polla_id, PollaMatch.phase == phase)
        .all()
    }
    if not phase_match_ids:
        return

    participants = db.query(PollaParticipant).filter_by(polla_id=polla_id).all()
    counts: dict[int, int] = {}
    for p in participants:
        correct = sum(
            1 for pred in p.predictions
            if pred.polla_match_id in phase_match_ids and pred.is_correct
        )
        counts[p.id] = correct

    max_correct = max(counts.values()) if counts else 0
    if max_correct == 0:
        return

    for p in participants:
        if counts[p.id] == max_correct:
            p.bonus_points += bonus
            logger.info(
                f"[polla] Más aciertos fase {phase} +{bonus} → "
                f"participant {p.id} (user {p.user_id}) con {max_correct} correctos"
            )


def _maybe_finalize_polla(polla_id: int, just_finished_phase: str, db: Session) -> None:
    """Si se terminó la fase FINAL, actualiza rankings finales."""
    if just_finished_phase not in ("final", "third"):
        return

    # Solo finalizar cuando tanto 'final' como 'third' estén puntuados
    unscored_end = (
        db.query(PollaMatch)
        .filter(
            PollaMatch.polla_id == polla_id,
            PollaMatch.phase.in_(["final", "third"]),
            PollaMatch.is_scored == False,
        )
        .count()
    )
    if unscored_end > 0:
        return

    polla = db.get(Polla, polla_id)
    if not polla or polla.status == "finished":
        return

    _update_rankings(polla_id, db)

    polla.status = "finished"
    db.commit()
    logger.info(f"[polla] Polla {polla_id} finalizada")


def _update_rankings(polla_id: int, db: Session) -> None:
    """Asigna rank a cada participante por total_points desc."""
    participants = (
        db.query(PollaParticipant)
        .filter_by(polla_id=polla_id)
        .order_by(PollaParticipant.total_points.desc())
        .all()
    )

    rank = 1
    prev_pts = None
    prev_rank = 1
    for i, p in enumerate(participants):
        if p.total_points != prev_pts:
            rank = i + 1
        p.rank = rank
        prev_pts = p.total_points


def compute_polla_result_from_match(match, is_groups: bool) -> tuple[str | None, int | None]:
    """
    Dado un Match finalizado, devuelve (actual_result, actual_winner_id)
    para usar en PollaMatch.
    """
    if match.home_score is None or match.away_score is None:
        return None, None

    home = match.home_score
    away = match.away_score

    if is_groups:
        if home > away:
            return "L", None
        elif away > home:
            return "V", None
        else:
            return "E", None
    else:
        # En eliminatorias siempre hay ganador
        if home > away:
            return None, match.home_team_id
        elif away > home:
            return None, match.away_team_id
        else:
            # Empate en 90min/tiempo extra → definición por penaltis
            pen_home = match.penalty_home
            pen_away = match.penalty_away
            if pen_home is not None and pen_away is not None:
                if pen_home > pen_away:
                    return None, match.home_team_id
                else:
                    return None, match.away_team_id
            # Penaltis aún no sincronizados → esperar próxima sync
            return None, None


def auto_score_polla_matches_for_match(match_id: int, db: Session) -> None:
    """
    Busca todos los PollaMatches vinculados a este match y, si el partido
    terminó, llena el resultado y puntúa predicciones.
    Llamado desde sync_scores.py cuando un partido transiciona a Finalizado.
    """
    polla_matches = (
        db.query(PollaMatch)
        .filter(PollaMatch.match_id == match_id, PollaMatch.is_scored == False)
        .all()
    )

    if not polla_matches:
        return

    from app.models.competition.match import Match
    match = db.get(Match, match_id)
    if not match:
        return

    for pm in polla_matches:
        is_groups = pm.phase == "groups"
        actual_result, actual_winner_id = compute_polla_result_from_match(match, is_groups)

        if actual_result is None and actual_winner_id is None:
            continue

        pm.actual_result = actual_result
        pm.actual_winner_id = actual_winner_id
        db.commit()

        score_polla_match(pm.id, db)
