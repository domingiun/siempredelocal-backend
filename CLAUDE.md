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
    routes/polla/      ← Sistema de pollas mundialistas
    services/          ← Lógica de negocio
    services/polla_scoring_service.py ← Puntuación y bonificaciones de pollas
    utils/
      file_upload.py   ← Validación de MIME y tamaño
      storage.py       ← Cliente Supabase Storage

frontend/
  src/
    context/           ← AuthContext, WalletContext, etc.
    pages/             ← Páginas completas
    pages/articles/    ← ArticlePage.jsx (pública, /articles/:id)
    pages/admin/articles/ ← AdminArticlesPage.jsx (/admin/articles)
    pages/polla/       ← PollaLandingPage, PollaDashboardPage, PollaPredictionsPage
    pages/admin/polla/ ← PollaAdminPage.jsx (/admin/polla)
    pages/wallet/      ← WalletPage.jsx (/wallet)
    components/wallet/ ← WalletBalance.jsx (diseño oscuro glassmorphism)
    components/        ← Componentes reutilizables
    components/auth/   ← Login, Register, Auth.css (diseño oscuro)
    components/polla/  ← PromoModal.jsx (video promo en iframe)
    services/api.js    ← Axios configurado con withCredentials
  public/
    promo_polla_mundial.html ← Video promocional de la polla (Web Speech API, 10 escenas)
    mundial-bg.png           ← Fondo del video promo
    logo.png                 ← Logo SiempreDeLocal usado en el video promo
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
- **SVG está bloqueado** — puede contener `<script>` tags → XSS almacenado si el CDN sirve con `image/svg+xml`. Solo `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp` permitidos.
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

### CORS
- En producción (`DEBUG=false`), solo se permiten orígenes de `siempredelocal.com` y Vercel. **No incluir IPs locales** (`192.168.x.x`) en producción.
- En desarrollo (`DEBUG=true`), se agregan `localhost:5173` y `localhost:3000`.
- Configurado directamente en `app/main.py` con `os.getenv("DEBUG")` — `app/core/config.py` está vacío, no importar `settings` de ahí.

### Rate limiting
- Login: 10 intentos/minuto por IP
- Register: 5/minuto por IP
- Global: 200 req/minuto por IP (slowapi)

### Contraseñas
- Mínimo 8 caracteres, debe contener al menos una letra y un número
- Validado en `backend/app/schemas/user/user.py` con `@validator('password')` en `UserCreate`
- El frontend (`Register.jsx`) también valida con las mismas reglas para UX coherente

## Variables de entorno requeridas

### Backend (Railway)
```
SECRET_KEY=<hex 64 chars — genera con: python -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql+psycopg://...
SUPABASE_URL=https://asbcnidpjofqwgnmlbpx.supabase.co
SUPABASE_SERVICE_ROLE_KEY=<service role key de Supabase>
API_FOOTBALL_KEY=<api key de API-Sports / API-Football>
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
7. **Nunca** uses `print()` para debug — expone datos de usuarios en logs de producción. Usar `logger.debug()` o simplemente eliminar.
8. **Nunca** subas SVG** — bloqueado por riesgo de XSS almacenado

## Versiones críticas del backend

| Paquete | Versión mínima | Razón |
|---|---|---|
| `fastapi` | 0.115.6 | Versiones < 0.115 son incompatibles con Pydantic 2.5+ (`FieldInfo has no 'in_'`) |
| `pydantic` | 2.10.x | Requiere FastAPI 0.115+ para funcionar correctamente |
| `slowapi` | 0.1.9 | Rate limiting — requiere `request: Request` como primer param en endpoints limitados |

## Repositorios y despliegue

- **Backend** → `https://github.com/domingiun/siempredelocal-backend` (repo separado en `backend/`)
- **Frontend** → `https://github.com/domingiun/siempredelocal-frontend` (repo separado en `frontend/`)
- **Flujo de deploy:** `git push` en el repo de backend → Railway detecta el push y hace auto-deploy automáticamente (no hace falta trigger manual)
- Para commitear: `cd backend && git add <archivos> && git commit && git push`
- Para el frontend: `cd frontend && git add <archivos> && git commit && git push`

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
- `Polla` → configuración de una polla (nombre, estado, entry_credits, prize)
- `PollaMatch` → partido dentro de una polla (vincula match real, fase, close_at, resultado)
- `PollaParticipant` → usuario inscrito en una polla (base_points, bonus_points, total_points, rank)
- `PollaPrediction` → predicción individual de un participante para un partido de polla

## Módulo de Artículos (`/articles`)

- Endpoints públicos: `GET /articles/` (lista) y `GET /articles/{id}` (detalle)
- Endpoint admin lista: `GET /articles/admin/all` — **debe estar ANTES de `/{id}`** en el router o FastAPI intenta parsear "admin" como int
- Endpoints admin CRUD: `POST /articles/`, `PUT /articles/{id}`, `DELETE /articles/{id}`
- `ArticleListItem` incluye `content` (para preview en homepage) — si se quita, el homepage rompe con `Cannot read properties of undefined (reading 'slice')`
- Imágenes de artículo → `article-images/`, fotos de autor → `author-photos/`
- Si la tabla `articles` ya existe en la BD y se agregan columnas nuevas al modelo, `create_all` NO las agrega automáticamente — hacer `ALTER TABLE articles ADD COLUMN ...` manualmente en dev; en Railway/producción la tabla se crea fresh con todas las columnas

## Scheduler de sincronización de marcadores (`backend/app/tasks/scheduler.py`)

**NO revertir a `IntervalTrigger`.** El plan FREE de api-football tiene 100 req/día. Un interval de 10 min consume ~144 req/día solo, agotando la cuota antes de que empiece el primer partido.

### Patrón actual: `DateTrigger` por partido
- Al arrancar y cada día a las 00:05 UTC, `schedule_todays_matches()` escanea los próximos 30 h y programa un job con `DateTrigger(run_date=match.match_date)` por cada partido pendiente.
- Cada job llama `run_and_reschedule()`: sincroniza marcadores y, si quedan partidos activos, se reprograma a sí mismo en 15 min (`FOLLOWUP_MINUTES = 15`).
- Un partido se considera "activo" si su estado no es terminal y su `match_date` está entre `now - 3h` y `now` (`MAX_MATCH_DURATION = timedelta(hours=3)`).
- Con 21 partidos en un día: ~40–60 req totales en lugar de 144+.

### Herramientas de diagnóstico admin
- `GET /matches/admin/scheduler-status` → estado del scheduler, jobs activos, partidos próximos con flag `job_scheduled`
- `POST /matches/admin/reschedule-matches` → fuerza re-escaneo sin reiniciar el backend
- `GET /matches/admin/api-raw-test` → llama la API directamente y muestra ligas vistas vs trackeadas

## Matching de nombres de equipos (`backend/app/tasks/sync_scores.py`)

La función `names_match()` usa **partial containment** (no solo igualdad exacta):

```python
def names_match(name_a, name_b):
    a = normalize_name(name_a)
    b = normalize_name(name_b)
    if not a or not b: return False
    if a == b: return True
    shorter, longer = (a, b) if len(a) <= len(b) else (b, a)
    return len(shorter) >= 4 and shorter in longer
```

**Por qué:** La API devuelve "1899 Hoffenheim" pero nuestra BD guarda "Hoffenheim". Sin el containment check, el partido nunca se vincula y el marcador no se actualiza. No simplificar a `==`.

## Sistema de diseño del frontend

- **Homepage, Login y Register** comparten el mismo sistema visual oscuro: fondo `#060d18`, gradiente radial azul, card glassmorphism
- `components/auth/Auth.css` → estilos compartidos de Login y Register
- `pages/HomePage.css` → estilos del homepage editorial
- Las estadísticas del hero (acumulado, usuarios, fechas abiertas) vienen de `GET /bet-integration/stats` → campos `total_prize_pool`, `total_users`, `active_betdates`

## Módulo de Pronósticos de la Comunidad (`/bets/community`)

- **Propósito:** ver los pronósticos de todos los participantes en fechas cerradas/finalizadas — fomenta transparencia post-cierre y evita trampa pre-cierre.
- **Backend:** `GET /bet-integration/betdate/{betdate_id}/community` — retorna `{participants: [...], total_participants, betdate_name, betdate_status}`
  - Bloqueado con 403 si la fecha está en estado `open`
  - Cada participante incluye: `username`, `avatar_url`, `total_points`, `rank`, y lista de `predictions` con marcador pronosticado, real, puntos, y logos de equipos
- **Frontend:** `pages/bets/CommunityPredictionsPage.jsx` — dropdown de fechas cerradas, panels colapsables por participante ordenados por puntos
- **Ruta en App.jsx:** `/bets/community` debe estar **ANTES** de `/bets/:id` para que React Router no interprete "community" como un ID numérico
- **betService:** método `getCommunityPredictions(betDateId)` → `GET /bet-integration/betdate/${betDateId}/community`

## Navegación rápida a pronósticos

- El botón "Hacer Pronósticos" (Dashboard y Header) navega directamente a `/bets/{id}/place` de la fecha más reciente abierta
- Lógica: llama `betService.getBetDates()`, ordena por `start_datetime` desc, busca `status === 'open'`, si no hay abierta usa la primera de la lista
- Si el fetch falla, hace fallback a `/bets`

## Módulo Polla (`/polla` y `/mundial`)

### Modo Mundial (`VITE_POLLA_MODE=true`)
**Estado actual (Mayo 2026): ACTIVO — la app está en modo polla durante el Mundial.**

Cuando `VITE_POLLA_MODE=true` (variable en Vercel):
- `/` y `/home` redirigen a `/mundial`
- `/dashboard` redirige a `/mundial/dashboard`
- Sidebar oculta: Pronósticos, Partidos, Competencias, Equipos, Reportes
- Sidebar admin oculta: Competencias, Equipos, Reportes, Nueva Fecha de BetDate

**Al terminar el Mundial (≈ julio 2026) → restaurar modo normal:**
1. En Vercel → Settings → Environment Variables → cambiar `VITE_POLLA_MODE` a `false` (o eliminar la variable)
2. Redeploy automático → todo el sistema de apuestas/BetDates vuelve a estar visible
3. No hay cambios en el backend — todos los datos siguen intactos

### Performance del frontend
- **Lazy loading**: todas las páginas usan `React.lazy` + `Suspense` — Vite genera un chunk por ruta, el usuario solo descarga lo que navega
- **Cache en pollaService**: `listPollas`, `getPolla`, `getMyStatus` tienen TTL de 30 s — evita llamadas repetidas al navegar entre páginas de la polla. Se invalida automáticamente en operaciones de escritura (join, submit, adminUpdate)

### Video promocional (`PromoModal`)
- `PromoModal.jsx` se monta en `PollaLandingPage` y se muestra **siempre** al entrar a `/mundial`
- Embebe `promo_polla_mundial.html` en un iframe 360×640. El HTML usa **Web Speech API** (`speechSynthesis`) para narrar cada escena.
- El iframe comunica al padre con `postMessage('promo-skip', '*')` cuando el usuario hace click en "Saltar →"; el modal escucha el evento y llama `onClose`.
- **Autoplay restriction**: el HTML tiene un splash screen (botón "▶ Te explico cómo jugar") que sirve como gesto de usuario obligatorio para desbloquear `speechSynthesis`. Sin ese click, el audio no reproduce.
- Cada escena avanza cuando `utterance.onend` dispara (duración = largo de la narración). En modo silenciado, fallback de 15 s. Timer de seguro de 45 s por si `onend` no dispara en algún browser.
- **No usar `Content-Type` en iframe src** — se sirve como archivo estático desde `public/`.

### Rutas frontend
- `/mundial` → `PollaLandingPage.jsx` — landing pública con info, reglas y CTA de inscripción
- `/mundial/dashboard` → `PollaDashboardPage.jsx` — sin `?id`: selector de pollas; con `?id=X`: dashboard de esa polla
- `/mundial/predict` → `PollaPredictionsPage.jsx` — formulario de predicciones (requiere `?id=X`)
- `/admin/polla` → `PollaAdminPage.jsx` — gestión completa (crear, agregar partidos, puntuar, ranking)

### Selector de pollas (`/mundial/dashboard` sin `?id`)
- Muestra todas las pollas activas como tarjetas con: estado, premio, participantes, costo de entrada
- Si el usuario está inscrito: muestra su posición, puntos y predicciones pendientes; botón "Ver mi dashboard"
- Si no está inscrito: botón "Inscribirme" (descuenta créditos y redirige al dashboard con `?id=X`)
- Cada polla es completamente independiente — participantes, predicciones y rankings no se mezclan entre pollas

### Sistema de puntuación
| Fase | Predicción | Puntos |
|---|---|---|
| `groups` | L / E / V (resultado) | 1 pt |
| `r32`, `r16` | ¿Quién avanza? | 2 pts |
| `qf`, `sf`, `third`, `final` | ¿Quién avanza? | 3 pts |

**Bonificaciones** (calculadas automáticamente al completarse TODOS los partidos de una fase):
- **Racha**: 3+ predicciones consecutivas correctas en la misma fase (por `match_order`) → +1 pt (una vez por fase por participante)
- **Mejor de la fase**: quien más aciertos tenga en la fase → +5 pts (groups/r32) o +3 pts (r16+); si hay empate, todos los empatados reciben el bonus

### Página de predicciones (`PollaPredictionsPage`)
- Al cargar, salta automáticamente al **primer partido sin predicción guardada** (`findIndex(m => !savedInit[m.id])`).
- Los puntos de navegación están color-codeados por resultado guardado: 🔵 azul = L, 🟡 ámbar = E, 🔴 rojo = V, 🟢 verde = eliminatoria (winner). En desktop muestran la letra (9 px); en mobile solo el color.
- **No revertir a `current = 0`** — rompe la UX para usuarios con predicciones parciales.

### Ventana de predicciones
- `close_at = match_date - 1h` — se asigna automáticamente al agregar un partido a la polla
- Si `close_at is None` → se trata como **abierto** (no como cerrado). **No revertir esta lógica.**
- `predictions_pending` cuenta partidos donde `close_at is None OR now < close_at AND is_scored = False`

### Puntuación automática
- Cuando el scheduler actualiza un marcador a "Finalizado", llama `auto_score_polla_matches_for_match(match_id, db)`
- Esa función busca todos los `PollaMatch` vinculados al `match_id` real y los puntúa
- Las bonificaciones de fase se disparan cuando `unscored == 0` para esa fase
- Para pollas con partidos de competencias NO rastreadas por el scheduler → el admin puntúa manualmente con `POST /polla/admin/{id}/score-match/{pm_id}`

### "Ver picks" de otros participantes
- Botón 👁 en cada fila del ranking abre un modal con las predicciones del participante
- **Solo muestra partidos `is_scored = True`** — los partidos no jugados nunca se exponen
- Acceso restringido: solo participantes de la misma polla pueden ver los picks de otros (`GET /polla/{id}/participant/{user_id}/predictions`)
- Modal incluye: mini stats (posición, pts totales, aciertos/total) + tabla (partido, su pick, resultado real, pts)

### Modelos clave
- `Polla` → configuración general (nombre, estado, entry_credits, prize)
- `PollaMatch` → partido dentro de una polla (vincula `match_id` real + fase + `close_at` + resultado)
- `PollaParticipant` → usuario inscrito (base_points, bonus_points, total_points, rank)
- `PollaPrediction` → predicción individual de un participante para un partido
- `pollaService.js` → todos los métodos del frontend para consumir la API de pollas

### Servicio de puntuación (`backend/app/services/polla_scoring_service.py`)
- `score_polla_match(polla_match_id, db)` → puntúa predicciones y llama bonificaciones
- `_maybe_compute_phase_bonuses(polla_id, phase, db)` → solo actúa cuando todos los partidos de la fase están puntuados
- `auto_score_polla_matches_for_match(match_id, db)` → punto de entrada desde el scheduler

### Dashboard polla (`PollaDashboardPage.jsx`)
- `PredMatchCard` — tarjeta compartida entre "Mis predicciones" y "Picks de participante". Incluye chip de fase con colores (`PHASE_META`): groups=gris, r16/r32=azul, qf=violeta, sf=ámbar, final=dorado.
- `MyPredictionsTab` — predicciones ordenadas por `match_date` desc (más reciente primero).
- `ParticipantPicksModal` — modal "Ver picks de otro participante", también ordenado por `match_date` desc. Hereda chip de fase de `PredMatchCard`.

## Bracket de eliminatoria (`/standings/playoff-bracket`)

- **`get_knockout_bracket(competition_id, db)`** en `backend/app/services/standings_service.py` — lee las rondas de eliminatoria directamente de la BD. **NO computa posiciones ni ganadores dinámicamente** — devuelve los partidos tal como están cargados en cada ronda.
- Filtra rondas por `_KNOCKOUT_TYPES = {ROUND_OF, SEMIFINAL, FINAL, THIRD_PLACE}`. Las rondas de tipo `GROUP_STAGE` nunca entran al bracket.
- Respuesta: `{ ready, phases: [{ round_id, round_name, round_type, round_number, matches: [...] }] }` — estructura de fases, no campos fijos por ronda.
- **No revertir a cálculo dinámico desde posiciones de grupos** — los equipos en cada partido eliminatorio ya están asignados en la BD por el admin.

## Formulario de creación de jornadas (`CreateRoundPage.jsx`)

- **`RoundType` enum válido:** `regular`, `group_stage`, `round_of`, `semifinal`, `final`, `third_place`. **No existe `quarterfinal`** — enviar ese valor genera 422 en Pydantic.
- Cuartos de Final deben crearse con `round_type = "round_of"` (igual que 16avos y 8avos).
- Si se agrega una opción de tipo de jornada en el frontend, verificar que su `value` coincida exactamente con uno de los valores del enum del backend.

## Auto-fill ciudad→estadio en `MatchForm.jsx`

- `CITY_STADIUM_MAP` dentro de `MatchForm` mapea las 16 ciudades sede del Mundial 2026 a su estadio.
- Cuando `isWorldCup = true`, el campo **Ciudad** es un `<Select>`. Al seleccionar, `handleCityChange` llama `form.setFieldsValue({ stadium })`.
- Orden en el formulario: **Ciudad primero**, luego **Estadio**.
