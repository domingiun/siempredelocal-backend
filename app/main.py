# backend/app/main.py
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware
from app.db import engine, Base
from app.models import *
import os

# M6: Rate limiter global — por IP
limiter = Limiter(key_func=get_remote_address, default_limits=["200/minute"])

# Importar routers
from app.routes.bet.Bet import router as bet_router
from app.routes.bet.BetDate import router as betdate_router
from app.routes.bet.BetPlan import router as betplan_router
from app.routes.bet.BetPrediction import router as betprediction_router
from app.routes.bet.UserWallet import router as wallet_router
from app.routes.bet.integration import router as bet_integration_router
from app.routes.bet.ranking import router as bet_ranking_router
from app.routes.bet.finalize import router as bet_finalize_router
from app.routes.bet.transactions import router as bet_transactions_router
from app.routes.bet.pricing import router as bet_pricing_router
from app.routes.bet.financial import router as bet_financial_router


from app.routes.user import auth, users, profile
from app.routes.dashboard import router as dashboard_router
from app.routes.competitions import (competition,teams as competition_teams,matches,rounds, standings, stats)
from app.routes.teams import stats as team_stats
from app.routes.admin import system
from app.routes.content.articles import router as articles_router

app = FastAPI(
    title="SiempreDeLocal API",
    version="1.0.0",
    description="API para gestión de competencias de fútbol"
)


@app.on_event("startup")
async def startup():
    """
    Crea las tablas al arrancar en vez de al importar el módulo.
    Esto evita que un fallo de conexión a la DB mate el proceso antes
    de que FastAPI pueda siquiera responder un healthcheck.
    """
    try:
        Base.metadata.create_all(bind=engine)
        print("[startup] Tablas verificadas/creadas correctamente.")
    except Exception as e:
        print(f"[startup] ADVERTENCIA: No se pudo conectar a la base de datos: {e}")
        print("[startup] La app arranca de todas formas — revisa DATABASE_URL en Railway.")

# M6: Registrar rate limiter
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(SlowAPIMiddleware)

# C8: Los archivos ya no se sirven desde disco local.
# Las URLs de avatars/logos apuntan directamente a Supabase Storage (CDN público).

# Configurar CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:5173",
        "http://localhost:3000",
        "http://192.168.1.16:5173",
        "http://192.168.1.4:5173",
        "http://192.168.1.6:5173",
        "https://siempredelocal.com",
        "https://www.siempredelocal.com",
        "https://siempredelocal-frontend.vercel.app"
    ],
    allow_credentials=True,
    # M2: Restringir a métodos y headers necesarios — no usar "*"
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
    allow_headers=["Content-Type", "Authorization", "Accept", "X-Requested-With"],
)

# Incluir rutas de usuarios
app.include_router(auth.router)
app.include_router(users.router)

# Incluir rutas de equipos generales
app.include_router(team_stats.router)    # Estadísticas de equipos
app.include_router(dashboard_router)        # Dashboard

# Incluir rutas de competencias
app.include_router(competition.router)           # CRUD de competencias
app.include_router(competition_teams.router)     # Equipos en competencias (prefix: /competitions/{id}/teams)
app.include_router(matches.router)               # Partidos
app.include_router(rounds.router)                # Rondas
app.include_router(standings.router)             # Tablas de posiciones
app.include_router(stats.router)                 # Estadísticas de competencias
app.include_router(system.router)                # Rutas de administración del sistema
app.include_router(profile.router)               # Rutas de perfil de usuario

# Incluir rutas de pronósticos
app.include_router(bet_router)                  # Rutas de pronósticos
app.include_router(betdate_router)              # Rutas de fechas de pronósticos
app.include_router(betplan_router)              # Rutas de planes de pronósticos
app.include_router(betprediction_router)        # Rutas de predicciones de pronósticos
app.include_router(wallet_router)               # Rutas de mi cajon de usuario
app.include_router(bet_integration_router)      # Rutas de integración de pronósticos
app.include_router(bet_ranking_router)         # Rutas de ranking de pronósticos
app.include_router(bet_finalize_router)        # Rutas de finalización de fechas de pronósticos
app.include_router(bet_transactions_router)    # Rutas de transacciones de pronósticos
app.include_router(bet_pricing_router)         # Rutas de precios y planes de pronósticos
app.include_router(bet_financial_router)       # Rutas de resumen financiero
app.include_router(articles_router)            # Rutas de artículos del homepage

@app.get("/")
def read_root():
    return {
        "message": "Bienvenido a SiempreDeLocal API",
        "version": "1.0.0",
        "modules": {
            "auth": "/auth",
            "users": "/users",
            "teams": "/teams",
            "team_stats": "/teams/{id}/stats",
            "competitions": "/competitions",
            "competition_teams": "/competitions/{id}/teams",
            "matches": "/matches",
            "rounds": "/competitions/{id}/rounds",
            "standings": "/competitions/{id}/standings",
            "competition_stats": "/competitions/{id}/stats"
        }
    }
