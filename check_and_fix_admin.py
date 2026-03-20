# backend/check_and_fix_admin.py
import sys
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

from app.db import SessionLocal, engine
from app.models.user.user import User
from app.core.security import verify_password, get_password_hash
from sqlalchemy import text

def check_database():
    """Verifica la conexión y estructura de la base de datos"""
    print("🔍 Verificando base de datos...")
    
    try:
        with engine.connect() as conn:
            # Verificar si existe la tabla users
            result = conn.execute(text("""
                SELECT EXISTS (
                    SELECT FROM information_schema.tables 
                    WHERE table_name = 'users'
                )
            """))
            table_exists = result.scalar()
            
            if table_exists:
                print("✅ Tabla 'users' existe")
                
                # Contar usuarios
                result = conn.execute(text("SELECT COUNT(*) FROM users"))
                count = result.scalar()
                print(f"📊 Total usuarios: {count}")
                
                # Mostrar usuarios existentes
                result = conn.execute(text("SELECT id, username, email, is_admin FROM users"))
                users = result.fetchall()
                
                if users:
                    print("\n👥 Usuarios en la base de datos:")
                    for user in users:
                        print(f"   ID: {user[0]}, Username: '{user[1]}', Email: '{user[2]}', Admin: {user[3]}")
                else:
                    print("ℹ️  No hay usuarios en la base de datos")
            else:
                print("❌ Tabla 'users' NO existe")
                
    except Exception as e:
        print(f"⚠️  Error verificando base de datos: {e}")

def verify_admin_password():
    """Verifica la contraseña del usuario admin"""
    print("\n🔐 Verificando contraseña del admin...")
    
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        
        if not admin:
            print("❌ Usuario 'admin' no encontrado")
            return False
        
        print(f"✅ Usuario admin encontrado:")
        print(f"   ID: {admin.id}")
        print(f"   Username: {admin.username}")
        print(f"   Email: {admin.email}")
        print(f"   Hash almacenado: {admin.hashed_password[:30]}...")
        
        # Intentar verificar con la contraseña por defecto
        test_passwords = ["Admin123!", "admin123", "admin", "password", "Admin123"]
        
        for test_pwd in test_passwords:
            is_valid = verify_password(test_pwd, admin.hashed_password)
            print(f"   Probando '{test_pwd}': {'✅ VÁLIDO' if is_valid else '❌ inválido'}")
            
            if is_valid:
                print(f"\n🎉 La contraseña correcta es: '{test_pwd}'")
                return True
        
        print("\n❌ Ninguna contraseña de prueba funcionó")
        return False
        
    except Exception as e:
        print(f"⚠️  Error: {e}")
        return False
    finally:
        db.close()

def reset_admin_password():
    """Resetea la contraseña del admin a un valor conocido"""
    print("\n🔄 Reseteando contraseña del admin...")
    
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        
        if not admin:
            print("⚠️  Creando nuevo usuario admin...")
            admin = User(
                username="admin",
                email="admin@siempredelocal.com",
                full_name="Administrador del Sistema",
                is_active=True,
                is_admin=True
            )
        
        # Resetear a contraseña simple
        new_password = "admin123!"
        admin.hashed_password = get_password_hash(new_password)
        
        db.add(admin)
        db.commit()
        
        print(f"✅ Contraseña reset exitoso:")
        print(f"   Username: admin")
        print(f"   Nueva contraseña: {new_password}")
        print(f"   Email: {admin.email}")
        
        return True
        
    except Exception as e:
        print(f"❌ Error: {e}")
        db.rollback()
        return False
    finally:
        db.close()

def create_simple_admin():
    """Crea un admin simple usando SQL directo (bypassing ORM)"""
    print("\n⚡ Creando admin directo con SQL...")
    
    try:
        with engine.connect() as conn:
            # Primero eliminar si existe
            conn.execute(text("DELETE FROM users WHERE username = 'admin'"))
            
            # Insertar nuevo admin con hash simple
            # Hash para "admin123" usando bcrypt
            simple_hash = "$2b$12$EixZaYVK1fsbw1ZfbX3OXePaWxn96p36WQoeG6Lruj3vjPGga31lW"
            
            conn.execute(text("""
                INSERT INTO users (username, email, hashed_password, full_name, is_active, is_admin)
                VALUES ('admin', 'admin@siempredelocal.com', :hash, 'Administrador', true, true)
            """), {"hash": simple_hash})
            
            conn.commit()
            
            print("✅ Admin creado directamente con SQL")
            print("   Username: admin")
            print("   Password: admin123")
            print("   Email: admin@siempredelocal.com")
            
            return True
            
    except Exception as e:
        print(f"❌ Error SQL: {e}")
        return False

def test_login():
    """Prueba el login con diferentes métodos"""
    print("\n🧪 Probando login...")
    
    test_cases = [
        {"username": "admin", "password": "admin123"},
        {"username": "admin", "password": "Admin123!"},
        {"username": "admin", "password": "admin"},
        {"username": "admin", "password": "password"},
    ]
    
    db = SessionLocal()
    try:
        admin = db.query(User).filter(User.username == "admin").first()
        
        if not admin:
            print("❌ No existe usuario admin")
            return
            
        for test in test_cases:
            is_valid = verify_password(test["password"], admin.hashed_password)
            print(f"   Login '{test['username']}' / '{test['password']}': {'✅ VÁLIDO' if is_valid else '❌ inválido'}")
            
    finally:
        db.close()

def main():
    print("🔧 DIAGNÓSTICO DE USUARIO ADMIN 🔧")
    print("=" * 40)
    
    # 1. Verificar base de datos
    check_database()
    
    # 2. Verificar contraseña actual
    if verify_admin_password():
        print("\n✅ El admin ya tiene contraseña válida")
        test_login()
    else:
        print("\n🔄 Intentando corregir...")
        
        # Opción 1: Resetear contraseña
        if reset_admin_password():
            test_login()
        else:
            # Opción 2: Crear directamente con SQL
            create_simple_admin()
            test_login()
    
    print("\n" + "=" * 40)
    print("📋 RESUMEN:")
    print("   Para hacer login usar:")
    print("   - Username: admin")
    print("   - Password: admin123 (o la que aparezca como válida arriba)")
    print("\n🔗 Endpoint: POST /auth/login")
    print("   Body JSON: {\"username\": \"admin\", \"password\": \"admin123\"}")

if __name__ == "__main__":
    main()