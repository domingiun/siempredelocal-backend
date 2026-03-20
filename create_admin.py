# backend/create_admin.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.db import SessionLocal
from app.models.user.user import User
from app.core.security import get_password_hash

def create_admin_user():
    db = SessionLocal()
    try:
        # Verificar si ya existe
        existing = db.query(User).filter(User.username == "admin").first()
        
        if existing:
            print("✅ Usuario admin ya existe:")
            print(f"   ID: {existing.id}")
            print(f"   Username: {existing.username}")
            print(f"   Email: {existing.email}")
            return
        
        # Crear nuevo admin
        admin_user = User(
            username="admin",
            email="admin@siempredelocal.com",
            hashed_password=get_password_hash("Admin123!"),
            full_name="Administrador del Sistema",
            is_active=True,
            is_admin=True
        )
        
        db.add(admin_user)
        db.commit()
        
        print("👤 Usuario admin creado exitosamente:")
        print(f"   Username: admin")
        print(f"   Contraseña: Admin123!")
        print(f"   Email: admin@siempredelocal.com")
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
    finally:
        db.close()

if __name__ == "__main__":
    create_admin_user()