# backend/app/routes/teams/__init__.py
from .stats import router as stats_router

__all__ = [
    "stats_router"
]