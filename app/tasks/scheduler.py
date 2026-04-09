# backend/app/tasks/scheduler.py
"""
Scheduler de tareas periódicas con APScheduler (BackgroundScheduler).
Corre en un hilo separado sin bloquear el event loop de FastAPI.
"""
import logging
from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.interval import IntervalTrigger

logger = logging.getLogger(__name__)

_scheduler: BackgroundScheduler | None = None


def start_scheduler(session_factory) -> None:
    """
    Inicia el scheduler. Llamar desde el evento startup de FastAPI.
    El job de sync corre cada 5 minutos pero solo consume 1 request de API
    cuando hay partidos pendientes ese día (ver sync_scores.py).
    """
    global _scheduler

    if _scheduler and _scheduler.running:
        logger.warning("[scheduler] Ya estaba corriendo — ignorando start duplicado")
        return

    from app.tasks.sync_scores import sync_today_scores

    _scheduler = BackgroundScheduler(timezone="UTC")

    _scheduler.add_job(
        func=sync_today_scores,
        trigger=IntervalTrigger(minutes=10),
        args=[session_factory],
        id="sync_scores",
        name="Sync resultados api-football",
        replace_existing=True,
        misfire_grace_time=120,  # Si se pierde un ciclo, ejecutar con hasta 2 min de retraso
        max_instances=1,         # Nunca dos instancias simultáneas
    )

    _scheduler.start()
    logger.info("[scheduler] Iniciado — sync de resultados cada 10 minutos")


def stop_scheduler() -> None:
    """Detiene el scheduler limpiamente. Llamar desde el evento shutdown."""
    global _scheduler
    if _scheduler and _scheduler.running:
        _scheduler.shutdown(wait=False)
        logger.info("[scheduler] Detenido")


def trigger_sync_now(session_factory) -> dict:
    """
    Ejecuta la sincronización inmediatamente (para el botón admin).
    Retorna el resumen de la operación.
    """
    from app.tasks.sync_scores import sync_today_scores
    return sync_today_scores(session_factory)
