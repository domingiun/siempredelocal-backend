# backend/app/utils/validators.py 
import re
from typing import Optional, Dict, Any
from email_validator import validate_email as validate_email_, EmailNotValidError

def validate_email(email: str) -> bool:
    """Valida formato de email"""
    try:
        validate_email_(email)
        return True
    except EmailNotValidError:
        return False

def validate_password_strength(password: str) -> Dict[str, Any]:
    """Valida fortaleza de contraseña - LIMITADO A 72 CARACTERES"""
    errors = []
    warnings = []
    
    # ✅ Verificar longitud máxima para bcrypt
    if len(password) > 72:
        warnings.append("La contraseña será truncada a 72 caracteres para compatibilidad")
        # No es un error, solo advertencia
    
    # Verificar longitud mínima
    if len(password) < 6:
        errors.append("Debe tener al menos 6 caracteres")
    
    # Verificar fortaleza (opcional, puedes ajustar)
    if not re.search(r"[A-Z]", password):
        warnings.append("Se recomienda al menos una mayúscula")
    
    if not re.search(r"[a-z]", password):
        warnings.append("Se recomienda al menos una minúscula")
    
    if not re.search(r"\d", password):
        warnings.append("Se recomienda al menos un número")
    
    # Calcular score simple
    score = 0
    if len(password) >= 8: score += 1
    if len(password) >= 12: score += 1
    if re.search(r"[A-Z]", password): score += 1
    if re.search(r"[a-z]", password): score += 1
    if re.search(r"\d", password): score += 1
    if re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): score += 1
    
    return {
        "is_valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "score": score,
        "max_score": 6,
        "is_too_long": len(password) > 72
    }

def validate_username(username: str) -> bool:
    """Valida formato de username"""
    pattern = r"^[a-zA-Z0-9_-]{3,20}$"
    return bool(re.match(pattern, username))

def truncate_password_if_needed(password: str) -> str:
    """Trunca contraseña a 72 caracteres si es necesario"""
    if len(password) > 72:
        return password[:72]
    return password