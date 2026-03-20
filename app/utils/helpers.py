# backend/app/utils/helpers.py
from datetime import datetime
from typing import Optional

def now_str(fmt: str = "%Y-%m-%d %H:%M:%S") -> str:
    """
    Retorna la fecha y hora actual en string.
    """
    return datetime.utcnow().strftime(fmt)

def dict_clean(d: dict) -> dict:
    """
    Elimina keys con valores None
    """
    return {k: v for k, v in d.items() if v is not None}

def generate_slug(text: str) -> str:
    """
    Convierte un texto en slug simple.
    """
    return text.strip().lower().replace(" ", "-")
