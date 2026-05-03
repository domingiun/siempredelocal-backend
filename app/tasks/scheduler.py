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

    # El sync puede fallar (error de red, rate limit). Capturamos para siempre
    # llegar al bloque de reschedule y no dejar el scheduler huérfano.
    try:
        result = sync_today_scores(session_factory)
        logger.info(
            f"[scheduler] Sync ejecutado — updated={result['updated']} "
            f"skipped={result['skipped']} no_match={result['no_match']}"
        )
    except Exception as exc:
        logger.error(f"[scheduler] Error en sync (se intentará reschedule igual): {exc}")

    # ¿Quedan partidos en curso o que deberían estar en curso?
    db = session_factory()
    try:
        now_utc = datetime.utcnow()
        # Los match_date están en hora local Colombia (UTC-5). Convertimos "ahora"
        # a hora local para comparar correctamente.
        COLOMBIA_OFFSET = timedelta(hours=5)
        now_local = now_utc - COLOMBIA_OFFSET
        terminal = {MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value}

        # Caso 1: partidos cuyo match_date (hora local) está en la ventana de 3h
        in_window = db.query(Match).filter(
            Match.status.notin_(list(terminal)),
            Match.match_date <= now_local,
            Match.match_date >= now_local - MAX_MATCH_DURATION,
        ).count()

        # Caso 2: partidos marcados "En curso" en la BD sin importar cuándo empezaron
        in_progress = db.query(Match).filter(
            Match.status == MatchStatus.IN_PROGRESS.value,
        ).count()

        still_active = in_window + in_progress

        if still_active > 0:
            next_run = now_utc + timedelta(minutes=FOLLOWUP_MINUTES)
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
        now_utc = datetime.utcnow()
        # match_date está en hora local Colombia (UTC-5). Convertimos a hora local
        # para comparar con match_date, y convertimos match_date a UTC (+5h) para
        # los DateTrigger (APScheduler interpreta datetimes naïf en su timezone = UTC).
        COLOMBIA_OFFSET = timedelta(hours=5)
        now_local = now_utc - COLOMBIA_OFFSET
        terminal = {MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value}

        # Ventana: ahora hasta 30 horas adelante (comparamos en hora local Colombia)
        upcoming = db.query(Match).filter(
            Match.status.notin_(list(terminal)),
            Match.match_date >= now_local,
            Match.match_date <= now_local + timedelta(hours=30),
        ).all()

        for match in upcoming:
            job_id = _match_job_id(match.id)
            if _scheduler.get_job(job_id):
                continue  # ya programado

            # Convertir hora local Colombia → UTC para APScheduler
            run_date_utc = match.match_date + COLOMBIA_OFFSET
            if run_date_utc < now_utc:
                run_date_utc = now_utc + timedelta(seconds=5)

            _scheduler.add_job(
                func=run_and_reschedule,
                trigger=DateTrigger(run_date=run_date_utc),
                id=job_id,
                args=[session_factory],
                replace_existing=True,
                misfire_grace_time=300,
            )
            logger.info(
                f"[scheduler] Job programado: partido {match.id} a las "
                f"{match.match_date.strftime('%H:%M')} local "
                f"({run_date_utc.strftime('%H:%M')} UTC)"
            )
            scheduled += 1

        # Sync inmediato si hay partidos que YA empezaron (o marcados "En curso")
        # y aún no terminaron (cubre reinicios del servidor durante un partido).
        in_window = db.query(Match).filter(
            Match.status.notin_(list(terminal)),
            Match.match_date <= now_local,
            Match.match_date >= now_local - MAX_MATCH_DURATION,
        ).count()
        explicit_in_progress = db.query(Match).filter(
            Match.status == MatchStatus.IN_PROGRESS.value,
        ).count()

        if in_window + explicit_in_progress > 0:
            immediate_id = _followup_job_id(now_utc + timedelta(seconds=10))
            if not _scheduler.get_job(immediate_id):
                _scheduler.add_job(
                    func=run_and_reschedule,
                    trigger=DateTrigger(run_date=now_utc + timedelta(seconds=10)),
                    id=immediate_id,
                    args=[session_factory],
                    replace_existing=True,
                )
                logger.info(
                    f"[scheduler] Sync inmediato: {in_window} en ventana horaria, "
                    f"{explicit_in_progress} marcado(s) 'En curso'"
                )

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
