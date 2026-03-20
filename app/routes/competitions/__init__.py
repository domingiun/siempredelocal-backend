# backend/app/routes/competitions/__init__.py
from .competition import router as competition_router
from .teams import router as competition_teams_router
from .matches import router as matches_router
from .rounds import router as rounds_router
from .standings import router as standings_router
from .stats import router as stats_router

__all__ = [
    "competition_router", 
    "competition_teams_router",
    "matches_router", 
    "rounds_router",
    "standings_router",
    "stats_router"
]