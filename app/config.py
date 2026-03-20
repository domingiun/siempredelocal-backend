# backend/app/config.py
import os
from dotenv import load_dotenv

load_dotenv()

class Settings:
    # JWT Configuration
    SECRET_KEY = os.getenv("SECRET_KEY", "M2A0T0I0L0D1A24")
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

    DATABASE_URL = _raw_db_url

settings = Settings()
