# backend/app/tasks/scheduler.py
"""
Scheduler basado en tiempos exactos de partido.

Estrategia:
  1. Al arrancar, programa un job en la hora exacta de cada partido pendiente hoy/mañana.
  2. Cada job sincroniza resultados y, si el partido sigue en curso, se re-agenda en 15 min.
  3. Un job diario (00:05 UTC) re-escanea partidos nuevos para el día siguiente.
  4. El admin puede forzar un sync inmediato desde el panel.

Consumo FREE (100 req/día):
  - 1 request por cada ventana activa de 15 min
  - Ventana por partido: ~90-120 min → ~6-8 requests por partido
  - 21 partidos en el día con solapamientos: ~40-60 requests totales
"""
import logging
from datetime import datetime, timedelta

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from apscheduler.triggers.date import DateTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None

# Máximo tiempo que esperamos después del inicio del partido antes de desistir
MAX_MATCH_DURATION = timedelta(hours=3)
# Intervalo de follow-up mientras el partido está en curso
FOLLOWUP_MINUTES = 15


def _followup_job_id(run_dt: datetime) -> str:
    return f"followup_{run_dt.strftime('%Y%m%d_%H%M')}"


def _match_job_id(match_id: int) -> str:
    return f"match_start_{match_id}"


def run_and_reschedule(session_factory) -> None:
    """
    Ejecuta el sync y, si hay partidos aún en curso, se re-agenda en FOLLOWUP_MINUTES.
    """
    from app.tasks.sync_scores import sync_today_scores
    from app.models.competition.match import Match, MatchStatus

    result = sync_today_scores(session_factory)
    logger.info(
        f"[scheduler] Sync ejecutado — updated={result['updated']} "
        f"skipped={result['skipped']} no_match={result['no_match']}"
    )

    # ¿Quedan partidos en curso o que deberían estar en curso?
    db = session_factory()
    try:
        now = datetime.utcnow()
        terminal = {MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value}

        # Caso 1: partidos cuyo match_date está en la ventana de 3h (hora UTC almacenada)
        in_window = db.query(Match).filter(
            Match.status.notin_(list(terminal)),
            Match.match_date <= now,
            Match.match_date >= now - MAX_MATCH_DURATION,
        ).count()

        # Caso 2: partidos marcados "En curso" en la BD sin importar cuándo empezaron
        # (cubre partidos nocturnos Colombia almacenados con hora local, cuyo match_date
        # UTC puede estar > 3h atrás aunque el partido todavía esté en juego)
        in_progress = db.query(Match).filter(
            Match.status == MatchStatus.IN_PROGRESS.value,
            Match.match_date <= now + MAX_MATCH_DURATION,  # no futuros lejanos
        ).count()

        still_active = in_window + in_progress

        if still_active > 0:
            next_run = now + timedelta(minutes=FOLLOWUP_MINUTES)
            job_id = _followup_job_id(next_run)
            if _scheduler and not _scheduler.get_job(job_id):
                _scheduler.add_job(
                    func=run_and_reschedule,
                    trigger=DateTrigger(run_date=next_run),
                    id=job_id,
                    args=[session_factory],
                    replace_existing=True,
                    misfire_grace_time=120,
                )
                logger.info(f"[scheduler] Follow-up programado para {next_run.strftime('%H:%M')} UTC ({still_active} partido(s) activo(s))")
        else:
            logger.info("[scheduler] Sin partidos activos — no se agenda follow-up")
    finally:
        db.close()


def schedule_todays_matches(session_factory) -> int:
    """
    Escanea la BD y programa un job en la hora exacta de inicio de cada partido
    pendiente de hoy y mañana. Retorna cuántos jobs nuevos se programaron.
    """
    from app.models.competition.match import Match, MatchStatus

    if not _scheduler:
        return 0

    db = session_factory()
    scheduled = 0
    try:
        now = datetime.utcnow()
        terminal = {MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value}

        # Ventana: ahora hasta 30 horas adelante
        upcoming = db.query(Match).filter(
            Match.status.notin_(list(terminal)),
            Match.match_date >= now,
            Match.match_date <= now + timedelta(hours=30),
        ).all()

        for match in upcoming:
            job_id = _match_job_id(match.id)
            if _scheduler.get_job(job_id):
                continue  # ya programado

            run_date = match.match_date
            if run_date < now:
                run_date = now + timedelta(seconds=5)  # si ya pasó, ejecutar ya

            _scheduler.add_job(
                func=run_and_reschedule,
                trigger=DateTrigger(run_date=run_date),
                id=job_id,
                args=[session_factory],
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info(
                f"[scheduler] Job programado: partido {match.id} a las "
                f"{run_date.strftime('%Y-%m-%d %H:%M')} UTC"
            )
            scheduled += 1

        # También programar follow-up inmediato si hay partidos que YA empezaron
        # y aún no terminaron (por si el servidor se reinició durante un partido)
        in_progress = db.query(Match).filter(
            Match.status.notin_(list(terminal)),
            Match.match_date <= now,
            Match.match_date >= now - MAX_MATCH_DURATION,
        ).count()

        if in_progress > 0:
            immediate_id = _followup_job_id(now + timedelta(seconds=10))
            if not _scheduler.get_job(immediate_id):
                _scheduler.add_job(
                    func=run_and_reschedule,
                    trigger=DateTrigger(run_date=now + timedelta(seconds=10)),
                    id=immediate_id,
                    args=[session_factory],
                    replace_existing=True,
                )
                logger.info(f"[scheduler] Sync inmediato por {in_progress} partido(s) ya en curso")

    finally:
        db.close()

    return scheduled


def start_scheduler(session_factory) -> None:
    """
    Inicia el scheduler. Llamar desde el evento startup de FastAPI.
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.warning("[scheduler] Ya estaba corriendo — ignorando start duplicado")
        return

    _scheduler = BackgroundScheduler(timezone="UTC")

    # Job diario a las 00:05 UTC: escanea partidos del día y los agenda
    _scheduler.add_job(
        func=schedule_todays_matches,
        trigger=CronTrigger(hour=0, minute=5, timezone="UTC"),
        id="daily_scan",
        args=[session_factory],
        replace_existing=True,
        misfire_grace_time=300,
    )

    _scheduler.start()
    logger.info("[scheduler] Iniciado — jobs por partido (DateTrigger) + scan diario 00:05 UTC")

    # Agenda los partidos de hoy/mañana inmediatamente al arrancar
    count = schedule_todays_matches(session_factory)
    logger.info(f"[scheduler] {count} partido(s) programados al arrancar")


def stop_scheduler() -> None:
    """Detiene el scheduler limpiamente."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Detenido")


def trigger_sync_now(session_factory) -> dict:
    """
    Ejecuta la sincronización inmediatamente (para el botón admin).
    """
    from app.tasks.sync_scores import sync_today_scores
    return sync_today_scores(session_factory)


def reschedule_matches(session_factory) -> int:
    """
    Fuerza un re-escaneo de partidos. Útil después de crear/editar partidos.
    """
    return schedule_todays_matches(session_factory)
