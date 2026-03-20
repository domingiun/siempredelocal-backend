# backend/init_db.py
import os

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from passlib.context import CryptContext

# Configuración de la base de datos
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+psycopg://admin:admin123@localhost:5432/siempredelocal"
)
engine_kwargs = {}
if DATABASE_URL.startswith("sqlite"):
    engine_kwargs["connect_args"] = {"check_same_thread": False}
engine = create_engine(DATABASE_URL, **engine_kwargs)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# Crear tablas
from backend.app.models.user.user import Base
Base.metadata.create_all(bind=engine)
print("✅ Tablas creadas")

# Función para hashear
def get_password_hash(password):
    pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
    if len(password) > 72:
        password = password[:72]
    return pwd_context.hash(password)

# Crear sesión
db = SessionLocal()

# Verificar si ya existe admin
from backend.app.models.user.user import User

admin = db.query(User).filter(User.username == "admin").first()

if not admin:
    # Crear usuario admin
    admin_user = User(
        email="admin@siempredelocal.com",
        username="admin",
        full_name="Administrador Principal",
        hashed_password=get_password_hash("admin123"),
        role="admin"
    )
    
    db.add(admin_user)
    db.commit()
    print("✅ Usuario admin creado:")
    print("   Usuario: admin")
    print("   Contraseña: admin123")
    print("   Email: admin@siempredelocal.com")
    print("   Rol: admin")
else:
    print("ℹ️ Usuario admin ya existe")

# Mostrar todos los usuarios
users = db.query(User).all()
print(f"\n📋 Total de usuarios: {len(users)}")
for user in users:
    print(f"   - ID: {user.id}, Usuario: {user.username}, Email: {user.email}, Rol: {user.role}")

db.close()
