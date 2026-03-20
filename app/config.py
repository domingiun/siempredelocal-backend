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
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://admin:admin123@localhost:5432/siempredelocal"
    )

settings = Settings()
