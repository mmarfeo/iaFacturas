# IAFacturas — Documentación Técnica

> Versión: 1.0 · Última actualización: 24 de Abril 2026

---

## 1. Descripción General

**IAFacturas** es una aplicación web SaaS para extracción y validación de facturas electrónicas AFIP. Permite a usuarios subir PDFs de facturas, extraer automáticamente todos sus datos (CUIT, CAE, importes, fechas) y validar el CAE en tiempo real contra los servidores de AFIP.

**URL producción:** `https://iafacturas.dewoc.com`
**Repositorio:** `github.com/mmarfeo/iafacturas`
**Deploy:** VPS propio (mismo servidor que `document-ai`) vía Docker + Traefik

---

## 2. Stack Tecnológico

### Backend

| Tecnología | Versión | Rol |
|---|---|---|
| Python | 3.11 | Lenguaje base |
| FastAPI | 0.115.0 | Web framework async |
| Gunicorn + UvicornWorker | 23.0.0 / incluido | Servidor producción |
| SQLAlchemy | 2.0.36 | ORM async |
| asyncpg | 0.30.0 | Driver async para PostgreSQL |
| Alembic | 1.13.3 | Migraciones de base de datos |
| Pydantic v2 | 2.9.2 | Validación y settings |
| pydantic-settings | 2.5.2 | Variables de entorno tipadas |
| Jinja2 | 3.1.4 | Templates HTML server-side |
| python-multipart | latest | Upload de archivos |

### Procesamiento PDF / OCR

| Tecnología | Versión | Rol |
|---|---|---|
| pdfplumber | 0.11.4 | Extracción texto PDF nativo |
| pdf2image | 1.17.0 | Conversión PDF → imagen para OCR |
| pytesseract | 0.3.13 | OCR para PDFs escaneados |
| Tesseract OCR | sistema | Motor OCR (instalado en Docker) |
| poppler-utils | sistema | Dependencia de pdf2image |

### IA / LLM

| Tecnología | Versión | Rol |
|---|---|---|
| Ollama | host del VPS | LLM local (qwen2.5:7b por defecto) |
| httpx | 0.27.2 | Cliente HTTP async para Ollama y AFIP |
| OpenAI API | - | Fallback opcional si Ollama falla |

### Auth

| Tecnología | Versión | Rol |
|---|---|---|
| passlib[bcrypt] | 1.7.4 | Hashing de contraseñas |
| python-jose[cryptography] | 3.3.0 | JWT (HS256) en cookie HTTP-only |

### Cola de tareas

| Tecnología | Versión | Rol |
|---|---|---|
| Celery | 5.4.0 | Procesamiento async de PDFs en background |
| Redis | 5.1.1 | Broker Celery + caché AFIP + step tracking |
| redis.asyncio | incluido | Cliente async para FastAPI |

### Base de datos

| Tecnología | Versión | Rol |
|---|---|---|
| PostgreSQL | 16 | Base de datos principal |
| JSONB | - | Almacenamiento de datos extraídos variables |

### Exportación

| Tecnología | Versión | Rol |
|---|---|---|
| openpyxl | 3.1.5 | Generación de archivos Excel (.xlsx) |

### Frontend

| Tecnología | Versión | Rol |
|---|---|---|
| Bootstrap | 5.3.3 | Framework CSS (CDN) |
| Google Fonts Inter | - | Tipografía |
| Vanilla JS | - | Interactividad (upload, tabs, dark mode) |

### Infraestructura

| Tecnología | Rol |
|---|---|
| Docker + Docker Compose | Contenedores |
| Nginx | Reverse proxy interno (app → uvicorn:8000) |
| Traefik v3 | Reverse proxy externo + SSL |
| Let's Encrypt | Certificado SSL (válido hasta Jul 2026) |
| Hostinger DNS | A record `iafacturas.dewoc.com` → IP 212.85.23.150 |

---

## 3. Estructura del Proyecto

```
iafacturas/
├── app/
│   ├── core/
│   │   ├── config.py         # Settings con pydantic-settings (variables .env)
│   │   ├── database.py       # Engine async SQLAlchemy + get_db()
│   │   ├── security.py       # hash_password, verify_password, JWT
│   │   └── auth.py           # Dependency get_current_user (cookie → usuario)
│   ├── models/
│   │   ├── plan.py           # Tabla planes (Free, Pro, Empresa)
│   │   ├── usuario.py        # Tabla usuarios
│   │   ├── suscripcion.py    # Tabla suscripciones activas
│   │   ├── factura.py        # Tabla facturas (con JSONB datos_extraidos)
│   │   └── uso_mensual.py    # Tabla uso mensual por usuario
│   ├── routers/
│   │   ├── auth.py           # GET/POST /auth/login, /auth/register, /auth/logout
│   │   └── facturas.py       # Páginas app + upload + API + exports
│   ├── services/
│   │   ├── ocr.py            # Extracción texto PDF (pdfplumber + pytesseract)
│   │   ├── regex_afip.py     # Regex para campos AFIP
│   │   ├── extractor.py      # Pipeline principal (orquesta OCR + regex + LLM)
│   │   └── llm_extractor.py  # Fallback LLM (Ollama → OpenAI)
│   ├── static/
│   │   └── css/iafacturas.css  # Estilos custom (Bootstrap overrides + dark mode)
│   ├── templates/
│   │   ├── base.html           # Layout base (navbar, dark mode, Bootstrap)
│   │   ├── landing.html        # Landing page pública
│   │   ├── auth/
│   │   │   ├── login.html
│   │   │   └── register.html
│   │   └── app/
│   │       ├── dashboard.html
│   │       ├── upload.html
│   │       ├── resultado.html
│   │       ├── historial.html
│   │       └── planes.html
│   └── main.py               # App FastAPI + routers + static + lifespan
├── tasks/
│   ├── celery_app.py         # Config Celery (broker Redis, queue "facturas")
│   └── procesar_factura.py   # Tarea: OCR → regex → CAE → LLM → guardar DB
├── alembic/
│   ├── env.py                # Alembic async config
│   ├── script.py.mako        # Template de migraciones
│   └── versions/             # Migraciones versionadas
├── uploads/                  # Archivos PDF subidos (excluido de git)
├── docs/
│   ├── TECHNICAL.md          # Este archivo
│   └── USER-GUIDE.md         # Guía de usuario
├── nginx/nginx.conf          # Config Nginx (proxy a uvicorn:8000)
├── Dockerfile                # Python 3.11-slim + Tesseract + poppler
├── docker-compose.yml        # api + celery + postgres + redis + nginx
├── alembic.ini               # Config Alembic
├── requirements.txt          # Dependencias Python
└── .env.example              # Variables de entorno de ejemplo
```

---

## 4. Base de Datos

### Tablas principales

#### `planes`
| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | |
| nombre | VARCHAR(50) | Free, Pro, Empresa |
| limite_mensual | INTEGER NULL | NULL = ilimitado |
| precio | NUMERIC(10,2) | Precio mensual ARS |
| descripcion | TEXT | |

#### `usuarios`
| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | |
| email | VARCHAR(255) UNIQUE | |
| password_hash | VARCHAR(255) | bcrypt |
| nombre | VARCHAR(100) | |
| plan_id | FK → planes | |
| is_active | BOOLEAN | |
| is_verified | BOOLEAN | |
| created_at | TIMESTAMP | |

#### `facturas`
| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | También usado como job_id en Celery |
| usuario_id | FK → usuarios | |
| archivo_path | VARCHAR(500) | Ruta local del PDF |
| datos_extraidos | JSONB | Todos los campos extraídos |
| cae | VARCHAR(20) INDEX | CAE extraído |
| cae_valido | BOOLEAN | Resultado validación AFIP |
| cae_vencimiento | DATE | |
| cuit_emisor | VARCHAR(13) INDEX | |
| cuit_receptor | VARCHAR(13) | |
| importe | NUMERIC(12,2) | Importe total |
| fecha_factura | DATE | |
| estado | VARCHAR(20) | pendiente/procesando/completado/error |
| created_at | TIMESTAMP | |

#### `suscripciones`
| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | |
| usuario_id | FK → usuarios | |
| plan_id | FK → planes | |
| fecha_inicio | DATE | |
| fecha_vencimiento | DATE | |
| activa | BOOLEAN | |

#### `uso_mensual`
| Columna | Tipo | Descripción |
|---|---|---|
| id | INTEGER PK | |
| usuario_id | FK → usuarios | |
| mes | INTEGER | 1-12 |
| anio | INTEGER | ej: 2026 |
| cantidad_facturas | INTEGER | |

### Restricciones
- `uso_mensual`: UNIQUE(usuario_id, mes, anio)

---

## 5. Pipeline de Extracción

```
PDF subido
    │
    ▼
[ocr.py] pdfplumber
    │ ¿texto > 100 chars?
    ├─ Sí → texto nativo
    └─ No → pytesseract OCR (pdf2image, dpi=300, lang=spa)
    │
    ▼
[regex_afip.py] extraer_campos(texto)
    │ confidence = campos_clave_encontrados / 4
    │   clave = [cae, cuit_emisor, importe_total, fecha_emision]
    │
    ├─ confidence >= 0.5 → usar resultado regex
    │
    └─ confidence < 0.5 → [llm_extractor.py]
           │
           ├─ Ollama (ollama_url/api/generate, formato JSON)
           └─ OpenAI gpt-4o-mini (fallback si Ollama falla)
    │
    ▼
[Fase 5] afip.py validar_cae()
    │ Redis TTL=1h para cachear respuestas AFIP
    │
    ▼
Guardar en DB
    ├─ datos_extraidos (JSONB completo)
    └─ campos indexados (cae, cuit_emisor, importe, fecha_factura, etc.)
```

---

## 6. Autenticación

- **Mecanismo:** JWT (HS256) almacenado en cookie HTTP-only `access_token`
- **Expiración:** 7 días
- **Hashing:** bcrypt via passlib
- **Flujo:**
  1. POST `/auth/login` o `/auth/register` → valida credenciales → `set_cookie("access_token", token)`
  2. Cada request: `get_current_user` dependency lee la cookie, decodifica JWT, carga usuario desde DB
  3. GET `/auth/logout` → `delete_cookie("access_token")`

---

## 7. Tracking de Progreso Celery (Redis)

El upload JS hace polling a `GET /app/upload/estado/{job_id}` mientras el worker procesa.

| Clave Redis | Valor | TTL |
|---|---|---|
| `factura:{id}:step` | 0-4 (paso actual) | 1h |
| `factura:{id}:estado` | procesando/done/error | 1h |
| `factura:{id}:error` | mensaje de error | 1h |

**Pasos:**
| # | Descripción |
|---|---|
| 0 | Extrayendo texto con OCR |
| 1 | Aplicando regex AFIP |
| 2 | Validando CAE en AFIP |
| 3 | Procesando con IA (LLM) |
| 4 | Guardando resultado |

---

## 8. Variables de Entorno (.env)

| Variable | Obligatoria | Descripción |
|---|---|---|
| `SECRET_KEY` | ✅ | Clave para firmar JWT (mínimo 32 chars, generada con `python -c "import secrets; print(secrets.token_hex(32))"`) |
| `DATABASE_URL` | ✅ | `postgresql+asyncpg://user:pass@postgres:5432/iafacturas_db` |
| `POSTGRES_PASSWORD` | ✅ | Contraseña PostgreSQL (usada por el servicio Docker) |
| `REDIS_URL` | ✅ | `redis://redis:6379/0` |
| `APP_ENV` | - | `development` o `production` (default: production) |
| `OLLAMA_URL` | - | `http://host.docker.internal:11434` (default) |
| `OLLAMA_MODEL` | - | `qwen2.5:7b` (default) |
| `OLLAMA_ENABLED` | - | `true` / `false` (default: true) |
| `OPENAI_API_KEY` | - | Solo si se quiere usar OpenAI como fallback |
| `SMTP_HOST` | - | Para verificación de email (Fase 7) |
| `SMTP_PORT` | - | Default: 587 |
| `SMTP_USER` | - | |
| `SMTP_PASSWORD` | - | |
| `MERCADOPAGO_ACCESS_TOKEN` | - | Para pagos Pro (Fase 7) |
| `MERCADOPAGO_WEBHOOK_SECRET` | - | Para webhook de MercadoPago |

---

## 9. Deploy en Producción

### Servicios Docker

| Servicio | Puerto interno | Descripción |
|---|---|---|
| api | 8000 | FastAPI + Gunicorn (2 workers, timeout 120s) |
| celery | - | Worker Celery (cola "facturas") |
| postgres | 5432 | PostgreSQL 16 |
| redis | 6379 | Redis 7 |
| nginx | 8082 (host) | Proxy → api:8000 |

### Traefik
- Router: `iafacturas` → `websecure` entrypoint
- TLS: certificado Let's Encrypt extraído a `/root/certs-config/`
- Red Docker: `n8n_evoapi` (externa, compartida con n8n y evolution_api)
- Label clave: `traefik.docker.network=n8n_evoapi`

### Comandos de deploy

```bash
# Primer deploy
cd /root/iafacturas
cp .env.example .env
# Editar .env con valores reales
docker compose up -d --build

# Aplicar migraciones
docker compose exec api alembic upgrade head

# Ver logs
docker compose logs -f api
docker compose logs -f celery

# Rebuild tras cambios
docker compose up -d --build api celery
```

---

## 10. Patrones de Diseño

| Patrón | Dónde se usa |
|---|---|
| **Repository via SQLAlchemy** | Modelos ORM con relationships |
| **Dependency Injection** | `Depends(get_db)`, `Depends(get_current_user)` |
| **Async-first** | Todos los endpoints y operaciones DB son async |
| **Sync wrapper** | Servicios OCR/regex tienen versión sync para Celery |
| **Strategy** | Extracción: regex → LLM (estrategias intercambiables) |
| **Template Method** | Pipeline de extracción en `extractor.py` |
| **Circuit Breaker** | LLM falla silenciosamente, regex es fallback |
| **Optimistic DB write** | Celery usa `asyncio.run(_guardar(...))` |

---

## 11. Desarrollo Local

```bash
# Requisitos: Docker Desktop, Python 3.11+

# 1. Clonar y configurar
git clone git@github.com:mmarfeo/iafacturas.git
cd iafacturas
cp .env.example .env
# Editar .env (SECRET_KEY, POSTGRES_PASSWORD mínimo)

# 2. Levantar servicios
docker compose up -d --build

# 3. Aplicar migraciones
docker compose exec api alembic upgrade head

# 4. Verificar
curl http://localhost:8082/health
# → {"status":"ok","app":"IAFacturas","version":"1.0.0"}

# 5. Ver API docs (solo en APP_ENV=development)
open http://localhost:8082/api/docs
```

---

*IAFacturas — Dewoc · 2026*
