# backend/app/tasks/sync_scores.py
"""
Sincronización automática de resultados desde api-football.

Estrategia de matching (sin vinculación manual):
  1. Para cada partido nuestro que no esté finalizado/cancelado hoy:
     - Si ya tiene api_fixture_id guardado → match exacto (más rápido)
     - Si no → busca por nombre de equipo normalizado en los fixtures de la fecha
     - Si encuentra → guarda el api_fixture_id para futuras syncs
  2. Actualiza home_score, away_score y status.
  3. Dispara recálculo de standings/rondas/competencia.

Consumo FREE (100 req/día):
  - 1 request por ciclo de 10 min cuando hay partidos pendientes hoy.
  - Días sin partidos: 0 requests.
"""
import logging
import unicodedata
import re
from datetime import datetime, date, timedelta

from sqlalchemy.orm import Session, joinedload

from app.utils.api_football import get_fixtures_by_date
from app.models.competition.match import Match, MatchStatus
from app.services.competition_sync_service import sync_after_match_update

logger = logging.getLogger(__name__)

TERMINAL_STATUSES = {MatchStatus.FINISHED.value, MatchStatus.CANCELLED.value}


# ── Normalización de nombres ───────────────────────────────────────────────

def normalize_name(name: str) -> str:
    """
    Normaliza un nombre de equipo para comparación robusta:
    - Elimina tildes/acentos
    - Convierte a minúsculas
    - Elimina palabras genéricas (FC, CF, Club, de, etc.)
    - Elimina caracteres no alfanuméricos
    - Colapsa espacios
    """
    if not name:
        return ""

    # Eliminar acentos/tildes
    nfkd = unicodedata.normalize("NFKD", name)
    ascii_str = "".join(c for c in nfkd if not unicodedata.combining(c))

    result = ascii_str.lower()

    # Eliminar palabras genéricas comunes en nombres de clubes
    STOPWORDS = r"\b(fc|cf|sc|ac|bc|afc|bfc|sfc|fk|sk|nk|rsc|united|city|club|de|del|los|las|el|la|the|and|y)\b"
    result = re.sub(STOPWORDS, " ", result)

    # Solo letras y números
    result = re.sub(r"[^a-z0-9\s]", "", result)

    # Colapsar espacios
    result = re.sub(r"\s+", " ", result).strip()

    return result


def names_match(name_a: str, name_b: str) -> bool:
    """
    True si los nombres normalizados coinciden.
    Acepta coincidencia exacta o por contención (para casos como
    '1899 Hoffenheim' vs 'Hoffenheim', o 'FC Augsburg' vs 'Augsburg').
    Se exige que el token más corto tenga al menos 4 caracteres para
    evitar falsos positivos con nombres muy cortos.
    """
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if not a or not b:
        return False
    if a == b:
        return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 4 and shorter in longer


# ── Lógica de matching ─────────────────────────────────────────────────────

def find_fixture_for_match(match: Match, fixture_map: dict, all_fixtures: list) -> dict | None:
    """
    Busca el fixture de api-football que corresponde a un partido local.

    Prioridad:
    1. Si el partido ya tiene api_fixture_id → búsqueda directa (exacta).
    2. Si no → matching por nombre de equipo normalizado.
    """
    # Prioridad 1: ya vinculado previamente
    if match.api_fixture_id:
        return fixture_map.get(match.api_fixture_id)

    # Prioridad 2: matching por nombre
    home_name = match.home_team.name if match.home_team else ""
    away_name = match.away_team.name if match.away_team else ""

    if not home_name or not away_name:
        return None

    for f in all_fixtures:
        if names_match(home_name, f["home_team"]) and names_match(away_name, f["away_team"]):
            return f

    return None


# ── Verificación rápida en BD ──────────────────────────────────────────────

# ── Tarea principal ────────────────────────────────────────────────────────

def sync_today_scores(session_factory) -> dict:
    """
    Job principal: sincroniza marcadores y estados desde api-football.
    """
    db: Session = session_factory()
    result = {
        "date": date.today().isoformat(),
        "updated": 0,
        "skipped": 0,
        "no_match": 0,
        "errors": 0,
        "api_called": False,
        "fixtures_fetched": 0,
        "pending_in_db": 0,
    }

    try:
        # El scheduler solo llama esta función cuando hay partido activo.
        # Colombia = UTC-5: partidos nocturnos (≥ 19:00 hora local = ≥ 00:00 UTC del día siguiente)
        # se guardan con hora local pero api-football los devuelve bajo la fecha UTC siguiente.
        # Por eso buscamos en una ventana ampliada: ayer → mañana UTC.
        today     = datetime.utcnow().date()
        yesterday = today - timedelta(days=1)
        tomorrow  = today + timedelta(days=1)

        # Incluir también partidos marcados "En curso" aunque su match_date esté fuera
        # de la ventana normal (partidos nocturnos Colombia almacenados en hora local)
        from app.models.competition.match import MatchStatus as MS
        pending_window = (
            db.query(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .filter(
                Match.status.notin_(list(TERMINAL_STATUSES)),
                Match.match_date >= datetime.combine(yesterday, datetime.min.time()),
                Match.match_date <= datetime.combine(tomorrow, datetime.max.time()),
            )
            .all()
        )
        pending_in_progress = (
            db.query(Match)
            .options(joinedload(Match.home_team), joinedload(Match.away_team))
            .filter(Match.status == MS.IN_PROGRESS.value)
            .all()
        )
        # Combinar sin duplicados
        seen_ids = {m.id for m in pending_window}
        pending = pending_window + [m for m in pending_in_progress if m.id not in seen_ids]

        if not pending:
            logger.debug("[sync] Sin partidos pendientes — no se consume request")
            return result

        result["pending_in_db"] = len(pending)

        # Determinar qué fechas UTC necesitamos consultar en api-football.
        # Un partido guardado como "2026-04-12 20:30" hora Colombia (UTC-5) equivale a
        # "2026-04-13 01:30" UTC → api-football lo lista bajo 2026-04-13.
        # Detectamos esto: si match_date.hour >= 19 (hora almacenada local), el fixture
        # estará en el día siguiente UTC.
        COLOMBIA_EVENING_HOUR = 19  # a partir de las 7pm local el fixture cae en el día UTC siguiente
        dates_needed = {today.isoformat()}
        for m in pending:
            match_local_date = m.match_date.date() if m.match_date else None
            if match_local_date:
                dates_needed.add(match_local_date.isoformat())
                if m.match_date.hour >= COLOMBIA_EVENING_HOUR:
                    next_day = match_local_date + timedelta(days=1)
                    dates_needed.add(next_day.isoformat())

        # Fetchear fixtures para todas las fechas necesarias (máx. 2-3 fechas)
        all_fixtures: list = []
        for d_str in sorted(dates_needed):
            day_fixtures = get_fixtures_by_date(d_str)
            logger.info(f"[sync] api-football {d_str}: {len(day_fixtures)} fixture(s)")
            all_fixtures.extend(day_fixtures)

        result["api_called"] = True
        result["fixtures_fetched"] = len(all_fixtures)

        if not all_fixtures:
            logger.info("[sync] api-football no devolvió fixtures")
            return result

        fixture_map = {f["fixture_id"]: f for f in all_fixtures}
        fixtures = all_fixtures  # alias para find_fixture_for_match

        for match in pending:
            fixture = find_fixture_for_match(match, fixture_map, fixtures)

            if not fixture:
                logger.debug(
                    f"[sync] Sin fixture para partido {match.id} "
                    f"({getattr(match.home_team, 'name', '?')} vs "
                    f"{getattr(match.away_team, 'name', '?')})"
                )
                result["no_match"] += 1
                continue

            new_status = fixture["status"]
            new_home   = fixture["home_score"]
            new_away   = fixture["away_score"]

            # Guardar api_fixture_id si se encontró por nombre (para futuras syncs exactas)
            fixture_id_changed = match.api_fixture_id != fixture["fixture_id"]

            # Sin cambios → saltar
            if (not fixture_id_changed
                    and match.status == new_status
                    and match.home_score == new_home
                    and match.away_score == new_away):
                result["skipped"] += 1
                continue

            try:
                old_status = match.status

                match.home_score      = new_home
                match.away_score      = new_away
                match.status          = new_status
                match.api_synced_at   = datetime.utcnow()
                if fixture_id_changed:
                    match.api_fixture_id = fixture["fixture_id"]

                db.commit()
                db.refresh(match)

                sync_after_match_update(match=match, db=db)

                logger.info(
                    f"[sync] Partido {match.id} "
                    f"({getattr(match.home_team, 'name', '?')} vs "
                    f"{getattr(match.away_team, 'name', '?')}): "
                    f"{old_status} → {new_status} | {new_home}-{new_away}"
                )
                result["updated"] += 1

            except Exception as exc:
                db.rollback()
                logger.error(f"[sync] Error actualizando partido {match.id}: {exc}")
                result["errors"] += 1

    except Exception as exc:
        logger.error(f"[sync] Error general: {exc}")
    finally:
        db.close()

    logger.info(
        f"[sync] updated={result['updated']} skipped={result['skipped']} "
        f"no_match={result['no_match']} errors={result['errors']}"
    )
    return result
