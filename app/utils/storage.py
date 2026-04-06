# backend/app/utils/storage.py
"""
C8: Cliente de Supabase Storage.
Reemplaza el almacenamiento en disco local (ephemeral en Railway)
por almacenamiento persistente en la nube.

Bucket público "uploads" con tres carpetas:
  uploads/avatars/       → fotos de perfil de usuarios
  uploads/logos/         → logos de equipos
  uploads/competition-logos/ → logos de competencias
"""
import os
from supabase import create_client, Client

_SUPABASE_URL = os.environ.get("SUPABASE_URL", "")
_SUPABASE_KEY = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
BUCKET = "uploads"


def _client() -> Client:
    if not _SUPABASE_URL or not _SUPABASE_KEY:
        raise RuntimeError(
            "Faltan variables de entorno SUPABASE_URL o SUPABASE_SERVICE_ROLE_KEY"
        )
    return create_client(_SUPABASE_URL, _SUPABASE_KEY)


def upload_file(folder: str, filename: str, file_data: bytes, content_type: str = "image/jpeg") -> str:
    """
    Sube un archivo al bucket de Supabase Storage.

    Args:
        folder:       Subcarpeta dentro del bucket (ej: "avatars", "logos")
        filename:     Nombre del archivo (ya debe ser UUID — generado con generate_safe_filename)
        file_data:    Bytes del archivo
        content_type: MIME type real del archivo

    Returns:
        URL pública permanente del archivo subido
    """
    path = f"{folder}/{filename}"
    client = _client()

    # upsert=True sobreescribe si ya existe (útil al actualizar)
    client.storage.from_(BUCKET).upload(
        path=path,
        file=file_data,
        file_options={"content-type": content_type, "upsert": "true"},
    )

    # URL pública — el bucket está marcado como público en Supabase
    result = client.storage.from_(BUCKET).get_public_url(path)
    return result


def delete_file(folder: str, filename: str) -> None:
    """
    Elimina un archivo del bucket. Silencioso si no existe.

    Args:
        folder:   Subcarpeta (ej: "avatars")
        filename: Solo el nombre del archivo, sin la carpeta
    """
    if not filename:
        return
    try:
        path = f"{folder}/{filename}"
        _client().storage.from_(BUCKET).remove([path])
    except Exception:
        pass  # No bloqueamos la operación principal si el borrado falla


def extract_filename_from_url(public_url: str) -> str:
    """
    Extrae solo el nombre de archivo de una URL pública de Supabase.
    Ejemplo:
      https://xxx.supabase.co/storage/v1/object/public/uploads/avatars/abc123.jpg
      → "abc123.jpg"
    """
    return public_url.split("/")[-1] if public_url else ""
