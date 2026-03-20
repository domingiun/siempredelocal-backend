# backend/app/db.py
from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
import os
from dotenv import load_dotenv

# Cargar variables de entorno
load_dotenv()

# Configuración de base de datos
# Usar PostgreSQL local por defecto (más simple para desarrollo)
raw_db_url = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://admin:admin123@localhost:5432/siempredelocal"
)

# Railway suele entregar postgres:// o postgresql:// sin driver.
# Forzamos psycopg para SQLAlchemy 2.x.
if raw_db_url.startswith("postgres://"):
    raw_db_url = raw_db_url.replace("postgres://", "postgresql+psycopg://", 1)
elif raw_db_url.startswith("postgresql://"):
    raw_db_url = raw_db_url.replace("postgresql://", "postgresql+psycopg://", 1)

DATABASE_URL = raw_db_url

# Determinar si es SQLite o PostgreSQL
is_sqlite = "sqlite" in DATABASE_URL

if is_sqlite:
    # Configuración para SQLite
    engine = create_engine(
        DATABASE_URL,
        connect_args={"check_same_thread": False},
        echo=False,  # Cambiado de True a False para menos ruido
        pool_pre_ping=True
    )
else:
    # Configuración para PostgreSQL
    engine = create_engine(
        DATABASE_URL,
        echo=False,  # Cambiado de True a False para menos ruido
        pool_pre_ping=True,
        pool_size=20,
        max_overflow=30
    )

# Crear Base para modelos
Base = declarative_base()

# Configurar sesión
SessionLocal = sessionmaker(
    autocommit=False,
    autoflush=False,
    bind=engine
)

def get_db():
    """
    Dependencia para obtener sesión de base de datos.
    Uso en FastAPI:
    ```
    def my_endpoint(db: Session = Depends(get_db)):
        # usar db
    ```
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
