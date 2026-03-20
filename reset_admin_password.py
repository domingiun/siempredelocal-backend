# backend/reset_admin_password.py
import bcrypt
import os
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker

def reset_admin_password():
    """Restablecer la contraseña del admin directamente en la BD"""
    print("🔄 Restableciendo contraseña del admin...")
    
    # Configuración
    DATABASE_URL = os.getenv(
        "DATABASE_URL",
        "postgresql+psycopg://admin:admin123@localhost:5432/siempredelocal"
    )
    NEW_PASSWORD = "Admin123!"  # Nueva contraseña
    
    # Conectar a la BD
    engine_kwargs = {}
    if DATABASE_URL.startswith("sqlite"):
        engine_kwargs["connect_args"] = {"check_same_thread": False}
    engine = create_engine(DATABASE_URL, **engine_kwargs)
    
    # Generar hash con bcrypt
    if len(NEW_PASSWORD) > 72:
        NEW_PASSWORD = NEW_PASSWORD[:72]
    
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(NEW_PASSWORD.encode('utf-8'), salt)
    hashed_str = hashed.decode('utf-8')
    
    print(f"🔑 Nueva contraseña: {NEW_PASSWORD}")
    print(f"🔐 Hash generado: {hashed_str[:50]}...")
    
    try:
        with engine.connect() as conn:
            # Actualizar directamente en la BD
            conn.execute(
                text("UPDATE users SET hashed_password = :hash WHERE username = 'admin'"),
                {"hash": hashed_str}
            )
            conn.commit()
            
            # Verificar el cambio
            result = conn.execute(
                text("SELECT username, hashed_password FROM users WHERE username = 'admin'")
            ).fetchone()
            
            if result and result[1] == hashed_str:
                print("✅ Contraseña actualizada exitosamente")
                print(f"👤 Usuario: {result[0]}")
                print(f"🔍 Hash verificado: {result[1][:10]}...")
            else:
                print("❌ No se pudo verificar la actualización")
                
    except Exception as e:
        print(f"❌ Error: {e}")
        import traceback
        traceback.print_exc()

def verify_bcrypt_installation():
    """Verificar que bcrypt esté funcionando correctamente"""
    print("🔍 Verificando instalación de bcrypt...")
    
    try:
        import bcrypt
        
        # Prueba básica
        password = "test123"
        salt = bcrypt.gensalt()
        hashed = bcrypt.hashpw(password.encode(), salt)
        
        # Verificar
        if bcrypt.checkpw(password.encode(), hashed):
            print("✅ bcrypt funcionando correctamente")
            return True
        else:
            print("❌ bcrypt no verifica correctamente")
            return False
            
    except ImportError:
        print("❌ bcrypt no está instalado")
        print("💡 Instala con: pip install bcrypt")
        return False
    except Exception as e:
        print(f"❌ Error en bcrypt: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("🛠️  HERRAMIENTA DE RESET DE CONTRASEÑA ADMIN")
    print("=" * 50)
    
    if verify_bcrypt_installation():
        reset_admin_password()
