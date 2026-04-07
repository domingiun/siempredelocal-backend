# CLAUDE.md — SiempreDeLocal

Guía de contexto para Claude Code. Lee esto antes de tocar cualquier archivo.

## Qué es este proyecto

Plataforma de gestión de competencias de fútbol y pronósticos/apuestas.
- Usuarios registran predicciones de marcadores en fechas ("BetDates") de 10 partidos
- Pagan con créditos comprados vía Nequi (aprobación manual por admin)
- El ganador recibe el pozo acumulado en COP

## Stack

| Capa | Tecnología | Hosting |
|---|---|---|
| Backend | FastAPI + SQLAlchemy + PostgreSQL | Railway |
| Frontend | React 18 + Vite + Ant Design + Tailwind | Vercel |
| Storage | Supabase Storage (bucket `uploads`) | Supabase |
| Base de datos | PostgreSQL 15 | Railway (addon) |

## Estructura de carpetas clave

```
backend/
  app/
    routes/bet/        ← Sistema de pronósticos y wallets
    routes/user/       ← Auth, perfil, usuarios
    routes/competitions/ ← Competencias, equipos, partidos
    routes/content/    ← Artículos del homepage (articles.py)
    core/              ← JWT, dependencias, seguridad
    models/            ← SQLAlchemy ORM
    models/content/    ← Article
    schemas/           ← Pydantic request/response
    schemas/content/   ← ArticleResponse, ArticleListItem
    services/          ← Lógica de negocio
    utils/
      file_upload.py   ← Validación de MIME y tamaño
      storage.py       ← Cliente Supabase Storage

frontend/
  src/
    context/           ← AuthContext, WalletContext, etc.
    pages/             ← Páginas completas
    pages/articles/    ← ArticlePage.jsx (pública, /articles/:id)
    pages/admin/articles/ ← AdminArticlesPage.jsx (/admin/articles)
    components/        ← Componentes reutilizables
    components/auth/   ← Login, Register, Auth.css (diseño oscuro)
    services/api.js    ← Axios configurado con withCredentials
```

## Decisiones de arquitectura importantes

### Autenticación
- JWT en **httpOnly cookie** (`access_token`) — NO en localStorage
- Backend acepta cookie primero, Authorization Bearer como fallback (para Swagger)
- `get_current_user` en `app/core/security.py` maneja ambos casos

### Autorización
- `Depends(get_current_user)` → usuario autenticado
- `Depends(get_current_admin_user)` → solo ADMIN
- Frontend: `AdminRoute` component para rutas `/admin/*` y `/reports/*`
- **IMPORTANTE:** Toda validación real ocurre en el backend — el frontend es solo UX

### Wallets y transacciones financieras
- El `user_id` SIEMPRE se extrae de `current_user.id` (JWT), nunca del request body
- `SELECT FOR UPDATE` en todas las lecturas de wallet antes de descontar créditos
- La tasa de conversión COP/crédito es interna al servicio — nunca la controla el cliente
- Tabla `audit_log` inmutable para todas las operaciones admin (solo INSERT, nunca UPDATE/DELETE)

### Uploads de archivos
- Todo va a **Supabase Storage** (bucket `uploads`, carpetas `avatars/`, `logos/`, `competition-logos/`, `article-images/`, `author-photos/`)
- Validación: extensión + magic bytes reales (no solo extensión) — `validate_image_mime(file_data[:16], file_ext)`
- Límite: 10 MB por archivo
- Nombres: UUID4 (no predecibles, no contienen datos del usuario)
- **`upload_file()` es síncrono** — siempre llamar con `await run_in_threadpool(upload_file, ...)` desde handlers async para no bloquear el event loop

### Uploads desde el frontend
- Con `FormData`, **nunca** setear `Content-Type` manualmente en axios — el browser lo genera con el boundary correcto
- El header default `Content-Type: application/json` del `api` instance interfiere con multipart; usar `fetch` nativo para uploads con `credentials: 'include'`
- Ejemplo correcto:
  ```js
  await fetch(`${BASE}/endpoint/`, { method: 'POST', credentials: 'include', body: formData });
  ```

### Autorización — dónde vive cada función
- `get_current_user` → `app/core/security.py`
- `get_current_admin_user` → `app/core/dependencies.py` (NO en security.py)

### Rate limiting
- Login: 10 intentos/minuto por IP
- Register: 5/minuto por IP
- Global: 200 req/minuto por IP (slowapi)

## Variables de entorno requeridas

### Backend (Railway)
```
SECRET_KEY=<hex 64 chars — genera con: python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql+psycopg://...
SUPABASE_URL=https://asbcnidpjofqwgnmlbpx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role key de Supabase>
DEBUG=False
```

### Frontend (Vercel)
```
VITE_API_URL=https://<tu-backend>.railway.app
```

## Cómo correr en desarrollo local

```bash
# Backend
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000

# Frontend
cd frontend
npm install
npm run dev
```

O con Docker:
```bash
docker-compose up
```

## Reglas para no romper nada

1. **Nunca** aceptes `user_id` del request body en endpoints de wallet/apuestas — usa `current_user.id`
2. **Nunca** elimines `Depends(get_current_user)` o `Depends(get_current_admin_user)` de endpoints financieros
3. **Nunca** guardes archivos en disco local — usa `app/utils/storage.py`
4. **Nunca** añadas un default a `SECRET_KEY` en `config.py`
5. El `audit_log` es inmutable — solo INSERT, nunca UPDATE ni DELETE
6. El token JWT va en cookie, no en localStorage — no revertir esto

## Versiones críticas del backend

| Paquete | Versión mínima | Razón |
|---|---|---|
| `fastapi` | 0.115.6 | Versiones < 0.115 son incompatibles con Pydantic 2.5+ (`FieldInfo has no 'in_'`) |
| `pydantic` | 2.10.x | Requiere FastAPI 0.115+ para funcionar correctamente |
| `slowapi` | 0.1.9 | Rate limiting — requiere `request: Request` como primer param en endpoints limitados |

## Gotchas de Railway

- **`${{Service.VAR}}` solo funciona dentro del mismo proyecto.** Si el backend y el Postgres están en proyectos Railway distintos, la referencia se resuelve vacía → `DATABASE_URL` queda vacía → el engine se conecta a `localhost` → crash. Solución: copiar la `DATABASE_PUBLIC_URL` del Postgres y pegarla directamente como valor (no como referencia).
- **`DATABASE_URL` interna (`*.railway.internal`) no es accesible entre proyectos.** Usar siempre la URL pública cuando los servicios están en proyectos distintos.
- **`Base.metadata.create_all` NO debe estar a nivel de módulo.** Está en el evento `startup` de FastAPI con try/except — si se mueve al nivel de módulo, un fallo de conexión a la DB al arrancar mata el proceso antes de que FastAPI pueda responder cualquier healthcheck.

## Modelos críticos

- `UserWallet` → créditos y balance COP del usuario
- `BetDate` → fecha de pronósticos (10 partidos, estado: open/closed/finished)
- `Bet` → una apuesta de un usuario en un BetDate
- `BetPrediction` → cada uno de los 10 marcadores pronosticados
- `Transaction` → registro de movimientos financieros
- `AuditLog` → registro inmutable de acciones admin
- `Article` → artículo del homepage creado por admin (título, contenido, imagen, autor)

## Módulo de Artículos (`/articles`)

- Endpoints públicos: `GET /articles/` (lista) y `GET /articles/{id}` (detalle)
- Endpoint admin lista: `GET /articles/admin/all` — **debe estar ANTES de `/{id}`** en el router o FastAPI intenta parsear "admin" como int
- Endpoints admin CRUD: `POST /articles/`, `PUT /articles/{id}`, `DELETE /articles/{id}`
- `ArticleListItem` incluye `content` (para preview en homepage) — si se quita, el homepage rompe con `Cannot read properties of undefined (reading 'slice')`
- Imágenes de artículo → `article-images/`, fotos de autor → `author-photos/`
- Si la tabla `articles` ya existe en la BD y se agregan columnas nuevas al modelo, `create_all` NO las agrega automáticamente — hacer `ALTER TABLE articles ADD COLUMN ...` manualmente en dev; en Railway/producción la tabla se crea fresh con todas las columnas

## Sistema de diseño del frontend

- **Homepage, Login y Register** comparten el mismo sistema visual oscuro: fondo `#060d18`, gradiente radial azul, card glassmorphism
- `components/auth/Auth.css` → estilos compartidos de Login y Register
- `pages/HomePage.css` → estilos del homepage editorial
- Las estadísticas del hero (acumulado, usuarios, fechas abiertas) vienen de `GET /bet-integration/stats` → campos `total_prize_pool`, `total_users`, `active_betdates`
