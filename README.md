# Backend - SiempreDeLocal

API de gestión de competencias de fútbol y pronósticos.

## Módulos principales
- Autenticación JWT y gestión de usuarios (roles Admin/User, perfil, soft delete)
- Competencias: equipos, partidos, rondas, standings y estadísticas
- Dashboard
- Pronósticos: planes, predicciones, ranking, transacciones, pricing, resumen financiero
- Archivos estáticos en `/static` (uploads)

## Requisitos
- Python 3.10+
- PostgreSQL 15+ (recomendado)
- SQLite (legacy)

## Configuración
1. Crea el archivo `.env`:
```bash
copy .env.example .env
```

2. Ajusta `DATABASE_URL` en `backend/.env` si usarás PostgreSQL.

## Ejecutar en desarrollo (local)
```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload
```

## Ejecutar con Docker (desde la raíz)
```bash
docker-compose up -d db
```

El servicio backend está definido en `docker-compose.yml`. Para desarrollo usa `--reload`.

## Migración de SQLite a PostgreSQL
1. Levanta PostgreSQL (puedes usar `docker-compose up -d db` desde la raíz).
2. Verifica que `backend/.env` tenga un `DATABASE_URL` de PostgreSQL.
3. Ejecuta la migración desde `backend/siempredelocal.db`:
```bash
cd backend
python migrate_sqlite_to_postgres.py
```
4. Si tu SQLite está en otra ruta, define `SQLITE_URL`:
```bash
set SQLITE_URL=sqlite:///./otro_archivo.db
python migrate_sqlite_to_postgres.py
```

## Endpoints base
- `GET /` (estado y listado de módulos)
- `POST /auth/login`
- `POST /auth/register`
- `GET /users`
- `GET /competitions`
- `GET /matches`

## Scripts útiles
- Crear tablas + admin inicial: `python init_db.py`
- Reset de password admin: `python reset_admin_password.py`
- Crear admin: `python create_admin.py`

## Notas de producción
- No usar `--reload`.
- Configurar CORS para dominios reales.
- Usar `SECRET_KEY` fuerte y credenciales seguras.
- Considerar un servidor ASGI (por ejemplo, Gunicorn + Uvicorn workers) y proxy reverso.
