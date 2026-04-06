# backend/app/config.py
import os
from urllib.parse import urlsplit, urlunsplit, parse_qsl, urlencode
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # JWT Configuration — SECRET_KEY OBLIGATORIA, sin valor por defecto
    # Genera una con: python -c "import secrets; print(secrets.token_hex(32))"
    SECRET_KEY: str = os.environ["SECRET_KEY"]  # Falla al arrancar si no está definida
    ALGORITHM = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 
    
    # Database
    _raw_db_url = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://admin:admin123@localhost:5432/siempredelocal"
    )

    # Normalizar URL de Railway para usar psycopg (SQLAlchemy 2.x)
    if _raw_db_url.startswith("postgres://"):
        _raw_db_url = _raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
    elif _raw_db_url.startswith("postgresql://"):
        _raw_db_url = _raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)

    # Forzar SSL en entornos remotos si no está definido
    if _raw_db_url.startswith("postgresql+psycopg://"):
        parts = urlsplit(_raw_db_url)
        host = parts.hostname or ""
        qs = dict(parse_qsl(parts.query))
        if host not in ("localhost", "127.0.0.1") and "sslmode" not in qs:
            qs["sslmode"] = "require"
            parts = parts._replace(query=urlencode(qs))
            _raw_db_url = urlunsplit(parts)

    DATABASE_URL = _raw_db_url

settings = Settings()
