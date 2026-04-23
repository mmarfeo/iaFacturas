# IAFacturas — Roadmap & Checklist

> **URL del producto:** [iafacturas.dewoc.com](https://iafacturas.dewoc.com/)
>
> **Hosting:** Hostinger (subdominio de dewoc.com — página por defecto activa)
>
> **Última actualización:** Abril 2026

---

## Descripción del Proyecto

Aplicación web **100% Python** bajo el subdominio `iafacturas.dewoc.com` (Hostinger) donde cualquier usuario pueda subir PDFs de facturas y obtener información extraída (datos, CAE, validación AFIP) via OCR, regex y LLM.

**Repo base:** `01-App-Dewoc-CrmIA-Web` → carpetas `consultarcae/` (lógica a migrar) y `document-ai/` (FastAPI — reutilizar extractores)

---

## Stack Tecnológico

**Framework elegido: FastAPI + SQLAlchemy + PostgreSQL**

| Capa | Tecnología | Justificación |
|------|-----------|--------------|
| Web framework | **FastAPI** | Ya está en uso en `document-ai/`. Async nativo, alto rendimiento, OpenAPI automático |
| ORM | **SQLAlchemy 2.x** | El más maduro de Python, soporta async, compatible con múltiples DBs |
| Migraciones | **Alembic** | Integración nativa con SQLAlchemy, migraciones versionadas |
| Base de datos | **PostgreSQL** | Escalable, soporta JSONB (ideal para guardar datos extraídos), full-text search nativo |
| Validación | **Pydantic v2** | Ya incluido en FastAPI, tipado estricto de datos |
| Templates HTML | **Jinja2** | Incluido en FastAPI, suficiente para el frontend server-side |
| Cache / Rate limit | **Redis** | Control de límites por plan (Free: 10/mes), sesiones, caché de consultas AFIP |
| Task queue | **Celery + Redis** | Para procesar PDFs pesados en background sin bloquear la API |
| Auth | **FastAPI-Users** | Registro, login, JWT, email verification — listo para usar |

> **¿Por qué no Django?** Django es excelente pero está orientado a monolitos síncronos. Para este producto que necesita procesar PDFs con OCR+LLM de forma concurrente, el modelo async de FastAPI escala mejor con menos recursos.
>
> **¿Por qué PostgreSQL y no MySQL?** PostgreSQL soporta el tipo `JSONB` de forma nativa (ideal para guardar el resultado variable de la extracción) y tiene full-text search incorporado sin plugins.

---

## Leyenda

> 🟢 Fácil · 🟡 Medio · 🔴 Complejo
>
> `[Python]` `[DevOps]` `[IA]` `[SQL]`

---

## Fase 1 — Definición del Producto y Hosting

- [x] 🟢 Nombre del producto: **IAFacturas**
- [x] 🟢 Subdominio definido y provisionado: `iafacturas.dewoc.com` (Hostinger — página por defecto activa)
- [ ] 🟡 `[DevOps]` Configurar el subdominio en Hostinger para apuntar a la aplicación Python (FastAPI via WSGI/proxy)
- [ ] 🟡 `[DevOps]` Verificar soporte de Python en el plan de Hostinger o evaluar si conviene usar un VPS/Docker aparte
- [ ] 🟢 Definir paleta de colores, logo y branding básico del producto (nombre: IAFacturas)
- [ ] 🟢 Definir planes y precios (Free: 10 facturas/mes, Pro: ilimitado, etc.)

---

## Fase 2 — Arquitectura y Setup del Proyecto

- [ ] 🟡 `[DevOps]` Crear repositorio Git separado para el producto (`iafacturas` o similar)
- [ ] 🟡 `[DevOps]` Crear `docker-compose.yml` con: `fastapi` + `postgresql` + `redis` + `celery` + `nginx`
- [ ] 🟡 `[Python]` Inicializar proyecto FastAPI con estructura:
  ```
  app/
  ├── core/          # config, database, security
  ├── models/        # SQLAlchemy models
  ├── schemas/       # Pydantic schemas
  ├── routers/       # endpoints
  ├── services/      # lógica de negocio (OCR, AFIP, LLM)
  └── templates/     # Jinja2 HTML
  tasks/             # Celery tasks
  alembic/           # migraciones
  ```
- [ ] 🟡 `[Python]` Configurar `requirements.txt`:
  ```
  fastapi
  uvicorn[standard]
  sqlalchemy[asyncio]
  alembic
  asyncpg
  redis
  celery
  pydantic[email]
  pydantic-settings
  python-jose[cryptography]
  passlib[bcrypt]
  fastapi-users[sqlalchemy]
  fastapi-mail
  httpx
  pytesseract
  pdf2image
  pdfplumber
  python-multipart
  openpyxl
  mercadopago
  ```
- [ ] 🟡 `[Python]` Configurar `app/core/config.py` con `pydantic-settings` para variables de entorno
- [ ] 🟡 `[Python]` Configurar conexión async a PostgreSQL con SQLAlchemy (`asyncpg` como driver)
- [ ] 🟢 `[DevOps]` Crear `.env.example` con todas las variables necesarias: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `MERCADOPAGO_ACCESS_TOKEN`, `SMTP_*`, `SECRET_KEY`

---

## Fase 3 — Modelos de Base de Datos y Migraciones

- [ ] 🟡 `[Python]` Crear modelo `Usuario`: `id`, `email`, `password_hash`, `nombre`, `plan_id`, `created_at`, `is_active`, `is_verified`
- [ ] 🟡 `[Python]` Crear modelo `Plan`: `id`, `nombre`, `limite_mensual`, `precio`, `descripcion`
- [ ] 🟡 `[Python]` Crear modelo `Suscripcion`: `id`, `usuario_id`, `plan_id`, `fecha_inicio`, `fecha_vencimiento`, `activa`
- [ ] 🟡 `[Python]` Crear modelo `Factura`: `id`, `usuario_id`, `archivo_path`, `datos_extraidos` (JSONB), `cae`, `cae_valido`, `cae_vencimiento`, `cuit_emisor`, `cuit_receptor`, `importe`, `fecha_factura`, `estado`, `created_at`
- [ ] 🟢 `[Python]` Crear modelo `UsoMensual`: `id`, `usuario_id`, `mes`, `año`, `cantidad_facturas`
- [ ] 🟢 `[Python]` Inicializar Alembic: `alembic init alembic`
- [ ] 🟢 `[Python]` Crear y aplicar primera migración con todos los modelos

---

## Fase 4 — Backend: OCR, Regex y Extracción de Datos

- [ ] 🟡 `[Python]` Migrar y adaptar lógica de `consultarcae/app/Models/` a servicios Python en `app/services/extractor.py`
- [ ] 🟡 `[Python]` Crear `app/services/ocr.py`: integrar `pytesseract` + `pdf2image` + `pdfplumber` para extracción de texto
- [ ] 🟡 `[Python]` Crear `app/services/regex_afip.py`: regex para:
  - CUIT emisor y receptor
  - Fecha de emisión
  - Número de factura (tipo + punto de venta + número)
  - Importe total
  - CAE
  - Fecha de vencimiento del CAE
- [ ] 🟡 `[Python]` Crear tarea Celery `tasks/procesar_factura.py` para procesamiento async en background
- [ ] 🔴 `[IA]` Crear `app/services/llm_extractor.py`: integrar LLM (Ollama o OpenAI) para extracción cuando regex no alcanza
- [ ] 🟡 `[Python]` Crear router `app/routers/facturas.py` con endpoints:
  - `POST /facturas/analizar` — recibe PDF, retorna job_id
  - `GET /facturas/{job_id}/estado` — estado del procesamiento
  - `GET /facturas/` — historial del usuario
  - `GET /facturas/{id}` — detalle de una factura
- [ ] 🟡 `[Python]` Guardar resultado de extracción como JSONB en campo `datos_extraidos` de la tabla `facturas`

---

## Fase 5 — Consulta CAE a AFIP

- [ ] 🟡 `[Python]` Crear `app/services/afip.py`: reescribir la lógica de `AfipQrDecoder.php` en Python usando `httpx` (async)
- [ ] 🟡 `[Python]` Implementar consulta al webservice AFIP con `httpx`:
  ```
  https://serviciosjava2.afip.gob.ar/sr-padron/webservices/personaServiceA5
  ```
- [ ] 🟡 `[Python]` Cachear respuestas de AFIP en Redis (TTL: 1 hora) para evitar sobrecarga
- [ ] 🟡 `[Python]` Crear router `app/routers/cae.py` con endpoint `GET /cae/validar?cae=X&cuit=Y`
- [ ] 🟡 `[Python]` Integrar validación de CAE automáticamente en el flujo de análisis de factura
- [ ] 🟢 Respuesta de validación estandarizada:
  ```json
  {
    "valido": true,
    "estado": "VIGENTE | VENCIDO | NO_ENCONTRADO",
    "cae": "12345678901234",
    "vencimiento": "2026-05-01"
  }
  ```

---

## Fase 6 — Frontend con Jinja2 + Tailwind

- [ ] 🟡 `[Python]` Configurar Jinja2 en FastAPI con `app/templates/` y `app/static/`
- [ ] 🟡 `[Python]` Crear `templates/base.html`: layout base con navbar, footer, Tailwind CSS via CDN
- [ ] 🟡 `[Python]` Crear `templates/landing.html`: hero, features, planes y precios, CTA
- [ ] 🟡 `[Python]` Crear `templates/auth/register.html` y `templates/auth/login.html`
- [ ] 🟡 `[Python]` Crear `templates/app/upload.html`: zona drag & drop de PDF con progreso (JS + fetch API)
- [ ] 🟡 `[Python]` Crear `templates/app/resultado.html`: datos extraídos en tarjetas, badge del CAE, botón descarga JSON/Excel
- [ ] 🟡 `[Python]` Crear `templates/app/historial.html`: tabla de facturas procesadas con filtros y paginación
- [ ] 🟢 `[Python]` Crear `templates/app/dashboard.html`: plan actual, facturas usadas este mes, últimas consultas

---

## Fase 7 — Autenticación, Planes y Pagos

- [ ] 🟡 `[Python]` Configurar `fastapi-users` con backend SQLAlchemy para registro, login y JWT
- [ ] 🟡 `[Python]` Implementar verificación de email al registrarse (SMTP via `fastapi-mail`)
- [ ] 🟡 `[Python]` Crear middleware/dependency `check_plan_limit()` que verifica uso mensual antes de procesar
- [ ] 🔴 `[Python]` Integrar MercadoPago Checkout Pro para suscripción al plan Pro
- [ ] 🟡 `[Python]` Webhook de MercadoPago: al pago exitoso → actualizar `suscripciones` en DB
- [ ] 🟢 `[Python]` Router `app/routers/planes.py`: ver planes, suscribirse, cancelar
- [ ] 🟢 `[Python]` Panel de usuario: plan actual, facturas usadas en el mes, historial de pagos

---

## Fase 8 — Deploy y Producción en iafacturas.dewoc.com

- [ ] 🟡 `[DevOps]` Decidir arquitectura de deploy en Hostinger: Python App (si el plan lo soporta) o VPS separado con Docker
- [ ] 🟡 `[DevOps]` Configurar SSL en `iafacturas.dewoc.com` con Let's Encrypt (Hostinger lo ofrece automáticamente)
- [ ] 🟡 `[DevOps]` Configurar Nginx/Apache como reverse proxy en Hostinger: `iafacturas.dewoc.com → uvicorn:8000`
- [ ] 🟡 `[DevOps]` Configurar `gunicorn` + `uvicorn workers` para producción:
  ```bash
  gunicorn -k uvicorn.workers.UvicornWorker app.main:app --workers 4
  ```
- [ ] 🟡 `[DevOps]` Configurar backups automáticos de PostgreSQL (pg_dump diario — Hostinger Backups o S3)
- [ ] 🟢 `[DevOps]` Activar monitoreo de uptime para `iafacturas.dewoc.com` en UptimeRobot
- [ ] 🟡 `[DevOps]` CI/CD con GitHub Actions: test → build Docker → deploy en push a `main`
- [ ] 🟢 Testing de carga: subir 50+ PDFs simultáneos y verificar que Celery distribuye correctamente
- [ ] 🟢 Verificar que la URL `https://iafacturas.dewoc.com` carga correctamente con SSL activo

---

## Resumen de Avance

| Fase | Descripción | Tareas | Completadas |
|------|-------------|--------|-------------|
| 1 | Producto y Hosting | 6 | 2 |
| 2 | Arquitectura y Setup | 7 | 0 |
| 3 | DB y Migraciones | 7 | 0 |
| 4 | OCR, Regex y Extracción | 7 | 0 |
| 5 | Consulta CAE AFIP | 6 | 0 |
| 6 | Frontend Jinja2 | 8 | 0 |
| 7 | Auth, Planes y Pagos | 7 | 0 |
| 8 | Deploy Producción | 9 | 0 |
| **Total** | | **57** | **2** |

---

*Generado el 23 de Abril de 2026 — Dewoc · IAFacturas*
