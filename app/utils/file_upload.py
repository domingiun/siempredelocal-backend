# backend/app/utils/file_upload.py
"""
Utilidades de seguridad para uploads de archivos.
A1: Validación de MIME real por magic bytes (sin depender solo de la extensión)
A2: Límite de tamaño enforced durante la lectura
M1: Nombres de archivo con UUID (no predecibles)
M3: Borrado seguro con protección contra path traversal
"""
import os
import uuid
from fastapi import HTTPException

MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024  # 10 MB (igual que system_config.json)

# Magic bytes de los formatos permitidos
# (primeros bytes que identifican el formato real del archivo)
_MAGIC_SIGNATURES: dict[str, list[bytes]] = {
    ".jpg":  [b"\xff\xd8\xff"],
    ".jpeg": [b"\xff\xd8\xff"],
    ".png":  [b"\x89PNG\r\n\x1a\n"],
    ".gif":  [b"GIF87a", b"GIF89a"],
    ".webp": [b"RIFF"],          # RIFF....WEBP — verificamos los 4 bytes adicionales
    # SVG eliminado: puede contener <script> tags → XSS almacenado si el CDN sirve con image/svg+xml
}

ALLOWED_EXTENSIONS = frozenset(_MAGIC_SIGNATURES.keys())


def validate_image_mime(file_header: bytes, extension: str) -> None:
    """
    A1: Verifica que los magic bytes del archivo coincidan con la extensión declarada.
    Lanza HTTPException 400 si el contenido no coincide con el formato anunciado.
    """
    ext = extension.lower()
    if ext not in _MAGIC_SIGNATURES:
        raise HTTPException(status_code=400, detail="Formato de archivo no permitido")

    signatures = _MAGIC_SIGNATURES[ext]
    matches = any(file_header.startswith(sig) for sig in signatures)

    # Caso especial WebP: RIFF....WEBP
    if ext == ".webp" and file_header.startswith(b"RIFF"):
        matches = file_header[8:12] == b"WEBP"

    if not matches:
        raise HTTPException(
            status_code=400,
            detail="El contenido del archivo no coincide con su extensión. "
                   "Por favor sube una imagen real.",
        )


async def read_with_size_limit(file) -> bytes:
    """
    A2: Lee el archivo completo respetando el límite de MAX_FILE_SIZE_BYTES.
    Lanza HTTPException 413 si el archivo supera el límite.
    """
    data = b""
    while True:
        chunk = await file.read(64 * 1024)  # 64 KB por chunk
        if not chunk:
            break
        data += chunk
        if len(data) > MAX_FILE_SIZE_BYTES:
            raise HTTPException(
                status_code=413,
                detail=f"El archivo supera el tamaño máximo permitido "
                       f"({MAX_FILE_SIZE_BYTES // (1024*1024)} MB).",
            )
    return data


def generate_safe_filename(extension: str) -> str:
    """
    M1: Genera un nombre de archivo usando UUID4.
    No predecible, no contiene datos del usuario ni timestamps.
    """
    return f"{uuid.uuid4().hex}{extension.lower()}"


def safe_delete_file(file_path: str, allowed_dir: str) -> None:
    """
    M3: Elimina un archivo validando que esté dentro del directorio permitido.
    Protege contra path traversal vía symlinks o rutas relativas.
    """
    try:
        real_file = os.path.realpath(file_path)
        real_allowed = os.path.realpath(allowed_dir)
        if not real_file.startswith(real_allowed + os.sep):
            # Silencioso — no exponemos la ruta al atacante
            return
        if os.path.isfile(real_file):
            os.remove(real_file)
    except Exception:
        pass  # No bloqueamos la operación principal si el borrado falla
