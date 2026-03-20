# backend/app/main.py
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from app.db import engine, Base
from app.models import *
import os

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

# Crear tablas
Base.metadata.create_all(bind=engine)

app = FastAPI(
    title="SiempreDeLocal API",
    version="1.0.0",
    description="API para gestión de competencias de fútbol"
)

# Archivos estáticos (logos, avatars)
os.makedirs("uploads", exist_ok=True)
app.mount("/static", StaticFiles(directory="uploads"), name="static")

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
    allow_methods=["*"],
    allow_headers=["*"],
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
