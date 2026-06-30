# backend/app/utils/api_football.py
"""
Cliente para api-football (v3.football.api-sports.io).
Plan FREE: 100 requests/día.

Variable de entorno requerida:
  API_FOOTBALL_KEY  → clave del dashboard de api-football
"""
import os
import logging
import httpx

logger = logging.getLogger(__name__)

API_KEY  = os.getenv("API_FOOTBALL_KEY", "")
BASE_URL = "https://v3.football.api-sports.io"

# IDs de ligas que manejamos en la plataforma
TRACKED_LEAGUES = {
    1,    # FIFA World Cup
    2,    # UEFA Champions League
    11,   # CONMEBOL Copa America
    13,   # CONMEBOL Libertadores
    14,   # CONMEBOL Sudamericana
    39,   # Premier League (England)
    71,   # Brasileirao Serie A (Brazil)
    78,   # Bundesliga (Germany)
    140,  # La Liga (Spain)
    239,  # Liga BetPlay Dimayor (Colombia)
}

# Mapeo de estados cortos de api-football → nuestros MatchStatus
STATUS_MAP: dict[str, str] = {
    "NS":   "Programado",   # Not Started
    "TBD":  "Programado",   # To Be Defined
    "1H":   "En curso",     # First Half
    "HT":   "En curso",     # Half Time
    "2H":   "En curso",     # Second Half
    "ET":   "En curso",     # Extra Time
    "BT":   "En curso",     # Break Time (extra time)
    "P":    "En curso",     # Penalty In Progress
    "INT":  "En curso",     # Interrupted
    "LIVE": "En curso",     # In Progress (generic)
    "FT":   "Finalizado",   # Full Time
    "AET":  "Finalizado",   # After Extra Time
    "PEN":  "Finalizado",   # After Penalties
    "AWD":  "Finalizado",   # Technical Loss
    "WO":   "Finalizado",   # WalkOver
    "PST":  "Aplazado",     # Postponed
    "SUSP": "Aplazado",     # Suspended
    "CANC": "Cancelado",    # Cancelled
    "ABD":  "Cancelado",    # Abandoned
}

FINISHED_STATUSES = {"FT", "AET", "PEN", "AWD", "WO"}


def is_configured() -> bool:
    return bool(API_KEY)


def _headers() -> dict:
    return {"x-apisports-key": API_KEY}


def get_fixtures_by_date(target_date: str) -> list[dict]:
    """
    Obtiene todos los fixtures para una fecha (YYYY-MM-DD) y filtra
    a las ligas de TRACKED_LEAGUES.

    Retorna lista de dicts con:
      fixture_id, league_id, status_short, status, home_score, away_score
    """
    if not is_configured():
        logger.warning("[api_football] API_FOOTBALL_KEY no configurada — saltando fetch")
        return []

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{BASE_URL}/fixtures",
                headers=_headers(),
                params={"date": target_date},
            )
            resp.raise_for_status()
            data = resp.json()

        all_items = data.get("response", [])
        api_errors = data.get("errors", {})

        if api_errors:
            logger.error(f"[api_football] Errores del API para {target_date}: {api_errors}")

        logger.info(
            f"[api_football] Total fixtures devueltos por API: {len(all_items)} "
            f"(errores: {api_errors})"
        )

        results = []
        for item in all_items:
            league_id = item["league"]["id"]
            if league_id not in TRACKED_LEAGUES:
                continue

            status_short = item["fixture"]["status"]["short"]
            home_score   = item["goals"]["home"]
            away_score   = item["goals"]["away"]
            penalty      = (item.get("score") or {}).get("penalty") or {}
            pen_home     = penalty.get("home")   # None si no hubo penaltis
            pen_away     = penalty.get("away")

            results.append({
                "fixture_id":   item["fixture"]["id"],
                "league_id":    league_id,
                "status_short": status_short,
                "status":       STATUS_MAP.get(status_short, "Programado"),
                "home_score":   home_score if home_score is not None else 0,
                "away_score":   away_score if away_score is not None else 0,
                "penalty_home": pen_home,
                "penalty_away": pen_away,
                "is_finished":  status_short in FINISHED_STATUSES,
                "home_team":    item["teams"]["home"]["name"],
                "away_team":    item["teams"]["away"]["name"],
            })

        logger.info(
            f"[api_football] {len(results)}/{len(all_items)} fixtures en ligas rastreadas para {target_date}"
        )
        return results

    except Exception as exc:
        logger.error(f"[api_football] Error obteniendo fixtures para {target_date}: {exc}")
        return []


def search_fixtures_for_admin(target_date: str) -> tuple[list[dict], dict]:
    """
    Retorna (fixtures_en_ligas_rastreadas, diagnostico).
    diagnostico incluye total_raw, api_errors, leagues_seen para debug.
    """
    if not is_configured():
        return [], {"error": "API_FOOTBALL_KEY no configurada"}

    try:
        with httpx.Client(timeout=15) as client:
            resp = client.get(
                f"{BASE_URL}/fixtures",
                headers=_headers(),
                params={"date": target_date},
            )
            resp.raise_for_status()
            data = resp.json()

        all_items = data.get("response", [])
        api_errors = data.get("errors", {})

        leagues_seen = list({item["league"]["id"] for item in all_items})

        diag = {
            "total_raw": len(all_items),
            "api_errors": api_errors,
            "leagues_seen": sorted(leagues_seen),
            "tracked_leagues": sorted(TRACKED_LEAGUES),
        }

        results = []
        for item in all_items:
            league_id = item["league"]["id"]
            if league_id not in TRACKED_LEAGUES:
                continue

            results.append({
                "fixture_id":  item["fixture"]["id"],
                "league":      item["league"]["name"],
                "league_id":   league_id,
                "league_country": item["league"].get("country"),
                "date":        item["fixture"]["date"],
                "venue":       item["fixture"]["venue"]["name"],
                "status_short": item["fixture"]["status"]["short"],
                "status":      STATUS_MAP.get(
                    item["fixture"]["status"]["short"], "Programado"
                ),
                "home_team":   item["teams"]["home"]["name"],
                "home_logo":   item["teams"]["home"]["logo"],
                "away_team":   item["teams"]["away"]["name"],
                "away_logo":   item["teams"]["away"]["logo"],
                "home_score":  item["goals"]["home"],
                "away_score":  item["goals"]["away"],
            })

        return results, diag

    except Exception as exc:
        logger.error(f"[api_football] Error en search_fixtures_for_admin: {exc}")
        return [], {"error": str(exc)}
