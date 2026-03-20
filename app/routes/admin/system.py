# backend/app/routes/admin/system.py
from fastapi import APIRouter, Depends, HTTPException, BackgroundTasks
from sqlalchemy.orm import Session
from typing import Dict, Any, List
import os
import shutil
import json
import subprocess
from datetime import datetime

from app.db import get_db
from app.models.user.user import User
from app.core.security import get_current_user
from app.core.dependencies import admin_required
from app.config import settings

router = APIRouter(prefix="/admin/system", tags=["admin-system"])

# Archivo de configuración del sistema
CONFIG_FILE = "system_config.json"

# Configuración por defecto
DEFAULT_CONFIG = {
    "app_name": "SiempreDeLocal",
    "version": "1.0.0",
    "environment": "development",
    "debug_mode": True,
    "maintenance_mode": False,
    "max_file_size": 10,  # MB
    "allowed_extensions": ["jpg", "png", "jpeg", "gif", "pdf"],
    "timezone": "America/Bogota",
    "language": "es",
    "email_enabled": False,
    "notifications_enabled": True,
    "backup_frequency": "daily",
    "session_timeout": 30,  # minutos
    "max_login_attempts": 5,
    "force_https": False,
    "log_access": True,
    "smtp_server": "",
    "smtp_port": 587,
    "smtp_ssl": True,
    "smtp_username": "",
    "smtp_password": "",
    "email_from": "noreply@siempredelocal.com",
    "email_template": "<html><body><h1>Notificación</h1><p>{{message}}</p></body></html>"
}

def load_config() -> Dict[str, Any]:
    """Cargar configuración del sistema desde archivo JSON"""
    try:
        if os.path.exists(CONFIG_FILE):
            with open(CONFIG_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        else:
            # Crear archivo con configuración por defecto
            save_config(DEFAULT_CONFIG)
            return DEFAULT_CONFIG
    except Exception as e:
        print(f"Error cargando configuración: {e}")
        return DEFAULT_CONFIG

def save_config(config: Dict[str, Any]) -> None:
    """Guardar configuración del sistema en archivo JSON"""
    try:
        with open(CONFIG_FILE, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    except Exception as e:
        print(f"Error guardando configuración: {e}")

@router.get("/config")
def get_system_config(
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Obtener configuración actual del sistema"""
    config = load_config()
    
    try:
        # Intentar importar psutil solo si está disponible
        import psutil
        # Obtener información del sistema en tiempo real
        system_info = {
            "system_time": datetime.now().isoformat(),
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": psutil.virtual_memory().percent,
            "disk_usage": psutil.disk_usage('/').percent,
            "uptime": int(psutil.boot_time()),
            "python_version": os.sys.version,
            "platform": os.sys.platform,
        }
    except ImportError:
        # Si psutil no está instalado, usar datos básicos
        system_info = {
            "system_time": datetime.now().isoformat(),
            "cpu_percent": 0,
            "memory_percent": 0,
            "disk_usage": 0,
            "uptime": 0,
            "python_version": os.sys.version,
            "platform": os.sys.platform,
        }
    
    return {
        "config": config,
        "system_info": system_info,
        "last_modified": os.path.getmtime(CONFIG_FILE) if os.path.exists(CONFIG_FILE) else None
    }

@router.put("/config")
def update_system_config(
    config_update: Dict[str, Any],
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Actualizar configuración del sistema"""
    current_config = load_config()
    
    # Validar campos permitidos
    allowed_fields = set(DEFAULT_CONFIG.keys())
    for key in config_update:
        if key not in allowed_fields:
            raise HTTPException(
                status_code=400,
                detail=f"Campo no permitido: {key}"
            )
    
    # Actualizar configuración
    current_config.update(config_update)
    save_config(current_config)
    
    return {
        "message": "Configuración actualizada exitosamente",
        "config": current_config
    }

@router.get("/stats")
def get_system_stats(
    db: Session = Depends(get_db),
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Obtener estadísticas del sistema"""
    from app.models.competition.competition import Competition
    from app.models.competition.team import Team
    from app.models.competition.match import Match
    from app.models.user.user import User
    
    # Contar registros en base de datos
    total_users = db.query(User).count()
    active_users = db.query(User).filter(User.is_active == True).count()
    total_competitions = db.query(Competition).count()
    active_competitions = db.query(Competition).filter(Competition.is_active == True).count()
    total_teams = db.query(Team).count()
    total_matches = db.query(Match).count()
    
    # Información de archivos
    upload_dir = "uploads"
    total_files = 0
    total_size = 0
    
    if os.path.exists(upload_dir):
        for root, dirs, files in os.walk(upload_dir):
            total_files += len(files)
            for file in files:
                file_path = os.path.join(root, file)
                if os.path.exists(file_path):
                    total_size += os.path.getsize(file_path)
    
    # Información del sistema
    try:
        import psutil
        disk_usage = psutil.disk_usage('/')
        memory = psutil.virtual_memory()
        
        system_info = {
            "cpu_percent": psutil.cpu_percent(),
            "memory_percent": memory.percent,
            "memory_total_gb": round(memory.total / (1024**3), 2),
            "memory_used_gb": round(memory.used / (1024**3), 2),
            "memory_free_gb": round(memory.free / (1024**3), 2),
            "uptime_days": int((datetime.now().timestamp() - psutil.boot_time()) / 86400),
        }
        
        storage_info = {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "disk_total_gb": round(disk_usage.total / (1024**3), 2),
            "disk_used_gb": round(disk_usage.used / (1024**3), 2),
            "disk_free_gb": round(disk_usage.free / (1024**3), 2),
            "disk_percent": disk_usage.percent,
        }
    except ImportError:
        # Si psutil no está instalado
        system_info = {
            "cpu_percent": 0,
            "memory_percent": 0,
            "memory_total_gb": 0,
            "memory_used_gb": 0,
            "memory_free_gb": 0,
            "uptime_days": 0,
        }
        
        storage_info = {
            "total_files": total_files,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "disk_total_gb": 0,
            "disk_used_gb": 0,
            "disk_free_gb": 0,
            "disk_percent": 0,
        }
    
    return {
        "database": {
            "total_users": total_users,
            "active_users": active_users,
            "total_competitions": total_competitions,
            "active_competitions": active_competitions,
            "total_teams": total_teams,
            "total_matches": total_matches,
        },
        "storage": storage_info,
        "system": system_info
    }

@router.post("/backup")
def create_system_backup(
    background_tasks: BackgroundTasks,
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Crear backup del sistema"""
    import zipfile
    import tempfile
    
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backups_dir = "backups"  # CORREGIDO: Definir variable
    os.makedirs(backups_dir, exist_ok=True)
    
    backup_file = os.path.join(backups_dir, f"backup_{timestamp}.zip")
    
    def create_backup_task():
        """Tarea en background para crear backup"""
        try:
            with zipfile.ZipFile(backup_file, 'w', zipfile.ZIP_DEFLATED) as zipf:
                # Backup de configuración
                if os.path.exists(CONFIG_FILE):
                    zipf.write(CONFIG_FILE, "system_config.json")
                
                # Backup de base de datos
                database_url = getattr(settings, "DATABASE_URL", "")
                if database_url.startswith("sqlite"):
                    db_file = settings.DATABASE_URL.replace("sqlite:///", "")
                    if os.path.exists(db_file):
                        zipf.write(db_file, "database.sqlite")
                elif database_url.startswith("postgresql"):
                    pg_dump_path = shutil.which("pg_dump")
                    if pg_dump_path:
                        tmp_sql_file = os.path.join(backups_dir, f"database_{timestamp}.sql")
                        pg_dump_command = [pg_dump_path, database_url, "-f", tmp_sql_file]
                        result = subprocess.run(pg_dump_command, capture_output=True, text=True)
                        if result.returncode == 0 and os.path.exists(tmp_sql_file):
                            zipf.write(tmp_sql_file, "database.sql")
                            os.remove(tmp_sql_file)
                        else:
                            print(f"No se pudo generar dump de PostgreSQL: {result.stderr.strip()}")
                    else:
                        print("pg_dump no disponible en el sistema. Se omite backup SQL de PostgreSQL.")
                elif hasattr(settings, 'sqlite_url'):
                    # Intentar con sqlite_url si existe
                    db_file = settings.sqlite_url.replace("sqlite:///", "")
                    if os.path.exists(db_file):
                        zipf.write(db_file, "database.sqlite")
                
                # Backup de uploads
                if os.path.exists("uploads"):
                    for root, dirs, files in os.walk("uploads"):
                        for file in files:
                            file_path = os.path.join(root, file)
                            arcname = os.path.relpath(file_path, "uploads")
                            zipf.write(file_path, os.path.join("uploads", arcname))
            
            # Registrar backup en archivo de logs
            backup_info = {
                "timestamp": timestamp,
                "file": backup_file,
                "size": os.path.getsize(backup_file) if os.path.exists(backup_file) else 0,
                "created_by": current_user.username if hasattr(current_user, 'username') else 'system'
            }
            
            backups_log = os.path.join(backups_dir, "backups_log.json")
            if os.path.exists(backups_log):
                with open(backups_log, 'r') as f:
                    logs = json.load(f)
            else:
                logs = []
            
            logs.append(backup_info)
            with open(backups_log, 'w') as f:
                json.dump(logs, f, indent=2)
                
        except Exception as e:
            print(f"Error creando backup: {e}")
    
    # Ejecutar en background
    background_tasks.add_task(create_backup_task)
    
    return {
        "message": "Backup iniciado en background",
        "backup_file": backup_file,
        "timestamp": timestamp
    }

@router.get("/backups")
def list_backups(
    current_user: User = Depends(admin_required)
) -> List[Dict[str, Any]]:
    """Listar backups disponibles"""
    backups_dir = "backups"  # CORREGIDO: Definir variable
    backups_log = os.path.join(backups_dir, "backups_log.json")
    
    if not os.path.exists(backups_log):
        return []
    
    try:
        with open(backups_log, 'r') as f:
            backups = json.load(f)
        
        # Verificar que los archivos existan
        valid_backups = []
        for backup in backups:
            if os.path.exists(backup.get("file", "")):
                valid_backups.append(backup)
        
        return valid_backups
        
    except Exception as e:
        print(f"Error leyendo backups: {e}")
        return []

@router.post("/cache/clear")
def clear_system_cache(
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Limpiar caché del sistema"""
    # Limpiar caché de Python
    import sys
    if hasattr(sys, 'getobjects'):
        import gc
        gc.collect()
    
    # Limpiar directorio de caché si existe
    cache_dir = "cache"
    if os.path.exists(cache_dir):
        shutil.rmtree(cache_dir)
        os.makedirs(cache_dir, exist_ok=True)
    
    return {
        "message": "Caché limpiada exitosamente",
        "timestamp": datetime.now().isoformat()
    }

@router.get("/logs")
def get_system_logs(
    lines: int = 100,
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Obtener logs del sistema"""
    log_file = "app.log"
    
    if not os.path.exists(log_file):
        return {"logs": [], "total_lines": 0}
    
    try:
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
        
        # Últimas N líneas
        recent_logs = all_lines[-lines:] if len(all_lines) > lines else all_lines
        
        return {
            "logs": recent_logs,
            "total_lines": len(all_lines),
            "showing_last": len(recent_logs)
        }
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error leyendo logs: {e}")

@router.post("/restart")
def restart_services(
    current_user: User = Depends(admin_required)
) -> Dict[str, Any]:
    """Reiniciar servicios del sistema"""
    # En producción, aquí reiniciarías los servicios
    # Por ahora solo simulamos
    return {
        "message": "Servicios reiniciados exitosamente",
        "timestamp": datetime.now().isoformat(),
        "note": "En producción se reiniciarían los servicios reales"
    }
