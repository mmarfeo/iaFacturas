# IAFacturas — Roadmap & Checklist

> **URL del producto:** [iafacturas.dewoc.com](https://iafacturas.dewoc.com/)
>
> **Hosting:** Hostinger (subdominio de dewoc.com — página por defecto activa)
>
> **Última actualización:** 24 de Abril 2026

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
| Auth | **JWT HTTP-only cookie** | Registro, login, JWT HS256 con passlib[bcrypt] — implementación custom |

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
- [x] 🟡 `[DevOps]` Configurar el subdominio en Hostinger para apuntar a la aplicación Python (DNS A record → VPS, website Hostinger eliminado)
- [x] 🟡 `[DevOps]` Verificar soporte de Python en el plan de Hostinger → decidido usar VPS existente con Docker
- [ ] 🟢 Definir paleta de colores, logo y branding básico del producto (nombre: IAFacturas)
- [ ] 🟢 Definir planes y precios (Free: 10 facturas/mes, Pro: ilimitado, etc.)

---

## Fase 2 — Arquitectura y Setup del Proyecto

- [x] 🟡 `[DevOps]` Crear repositorio Git separado para el producto (`github.com/mmarfeo/iafacturas`)
- [x] 🟡 `[DevOps]` Crear `docker-compose.yml` con: `fastapi` + `postgresql` + `redis` + `celery` + `nginx` + Traefik labels
- [x] 🟡 `[Python]` Inicializar proyecto FastAPI con estructura:
  ```
  app/
  ├── core/          # config, database, security
  ├── models/        # SQLAlchemy models
  ├── schemas/       # Pydantic schemas
  ├── routers/       # endpoints
  ├── services/      # lógica de negocio (OCR, AFIP, LLM)
  └── templates/     # Jinja2 HTML
  tasks/             # Celery tasks (celery_app.py + procesar_factura.py)
  alembic/           # migraciones
  ```
- [x] 🟡 `[Python]` Configurar `requirements.txt` con stack completo
- [x] 🟡 `[Python]` Configurar `app/core/config.py` con `pydantic-settings` para variables de entorno
- [x] 🟡 `[Python]` Configurar conexión async a PostgreSQL con SQLAlchemy (`asyncpg` como driver)
- [x] 🟢 `[DevOps]` Crear `.env.example` con todas las variables necesarias: `DATABASE_URL`, `REDIS_URL`, `OPENAI_API_KEY`, `MERCADOPAGO_ACCESS_TOKEN`, `SMTP_*`, `SECRET_KEY`

---

## Fase 3 — Modelos de Base de Datos y Migraciones

- [x] 🟡 `[Python]` Crear modelo `Usuario`: `id`, `email`, `password_hash`, `nombre`, `plan_id`, `created_at`, `is_active`, `is_verified`
- [x] 🟡 `[Python]` Crear modelo `Plan`: `id`, `nombre`, `limite_mensual`, `precio`, `descripcion`
- [x] 🟡 `[Python]` Crear modelo `Suscripcion`: `id`, `usuario_id`, `plan_id`, `fecha_inicio`, `fecha_vencimiento`, `activa`
- [x] 🟡 `[Python]` Crear modelo `Factura`: `id`, `usuario_id`, `archivo_path`, `datos_extraidos` (JSONB), `cae`, `cae_valido`, `cae_vencimiento`, `cuit_emisor`, `cuit_receptor`, `importe`, `fecha_factura`, `estado`, `created_at`
- [x] 🟢 `[Python]` Crear modelo `UsoMensual`: `id`, `usuario_id`, `mes`, `año`, `cantidad_facturas`
- [x] 🟢 `[Python]` Inicializar Alembic con `env.py` async + `script.py.mako`
- [x] 🟢 `[Python]` Crear y aplicar primera migración con todos los modelos + datos iniciales de planes

---

## Fase 4 — Backend: OCR, Regex y Extracción de Datos

- [x] 🟡 `[Python]` Migrar y adaptar lógica de `consultarcae/app/Models/` a servicios Python en `app/services/extractor.py`
- [x] 🟡 `[Python]` Crear `app/services/ocr.py`: integrar `pytesseract` + `pdf2image` + `pdfplumber` para extracción de texto
- [x] 🟡 `[Python]` Crear `app/services/regex_afip.py`: regex para:
  - CUIT emisor y receptor
  - Fecha de emisión
  - Número de factura (tipo + punto de venta + número)
  - Importe total
  - CAE
  - Fecha de vencimiento del CAE
- [x] 🟡 `[Python]` Crear tarea Celery `tasks/procesar_factura.py` para procesamiento async en background
- [x] 🔴 `[IA]` Crear `app/services/llm_extractor.py`: integrar LLM (Ollama → OpenAI fallback) para extracción cuando regex confidence < 0.5
- [x] 🟡 `[Python]` Crear router `app/routers/facturas.py` con endpoints:
  - `POST /app/upload` — recibe PDF, retorna job_id
  - `GET /app/upload/estado/{job_id}` — estado del procesamiento (polling)
  - `GET /app/historial` — historial paginado del usuario
  - `GET /app/facturas/{id}` — detalle de una factura
- [x] 🟡 `[Python]` Guardar resultado de extracción como JSONB en campo `datos_extraidos` de la tabla `facturas`

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

## Fase 6 — Frontend con Jinja2 + Bootstrap

- [x] 🟡 `[Python]` Configurar Jinja2 en FastAPI con `app/templates/` y `app/static/`
- [x] 🟡 `[Python]` Crear `templates/base.html`: layout base con navbar, footer, Bootstrap 5.3 via CDN + dark mode
- [x] 🟡 `[Python]` Crear `templates/landing.html`: hero, features, planes y precios, CTA
- [x] 🟡 `[Python]` Crear `templates/auth/register.html` y `templates/auth/login.html`
- [x] 🟡 `[Python]` Crear `templates/app/upload.html`: zona drag & drop de PDF con progreso (JS + polling)
- [x] 🟡 `[Python]` Crear `templates/app/resultado.html`: datos extraídos en tarjetas, badge del CAE, botón descarga JSON/Excel
- [x] 🟡 `[Python]` Crear `templates/app/historial.html`: tabla de facturas procesadas con filtros y paginación
- [x] 🟢 `[Python]` Crear `templates/app/dashboard.html`: plan actual, facturas usadas este mes, últimas consultas

---

## Fase 7 — Autenticación, Planes y Pagos

- [x] 🟡 `[Python]` Implementar auth con JWT HTTP-only cookie + bcrypt (custom, sin fastapi-users)
- [ ] 🟡 `[Python]` Implementar verificación de email al registrarse (SMTP via `fastapi-mail`)
- [x] 🟡 `[Python]` Crear dependency `check_plan_limit()` que verifica uso mensual antes de procesar
- [ ] 🔴 `[Python]` Integrar MercadoPago Checkout Pro para suscripción al plan Pro
- [ ] 🟡 `[Python]` Webhook de MercadoPago: al pago exitoso → actualizar `suscripciones` en DB
- [x] 🟢 `[Python]` Página de planes (`/planes`): ver planes disponibles con precios y características
- [x] 🟢 `[Python]` Panel de usuario: plan actual, facturas usadas en el mes (en dashboard)

---

## Fase 8 — Deploy y Producción en iafacturas.dewoc.com

- [x] 🟡 `[DevOps]` Decidir arquitectura de deploy → VPS existente con Docker (mismo VPS que document-ai)
- [x] 🟡 `[DevOps]` Configurar SSL en `iafacturas.dewoc.com` con Let's Encrypt via Traefik file provider (cert válido hasta Jul 2026)
- [x] 🟡 `[DevOps]` Configurar Traefik como reverse proxy: `iafacturas.dewoc.com → nginx container → uvicorn:8000`
- [x] 🟡 `[DevOps]` Configurar `gunicorn` + `uvicorn workers` para producción (2 workers, timeout 120s)
- [ ] 🟡 `[DevOps]` Configurar backups automáticos de PostgreSQL (pg_dump diario — Hostinger Backups o S3)
- [ ] 🟢 `[DevOps]` Activar monitoreo de uptime para `iafacturas.dewoc.com` en UptimeRobot
- [ ] 🟡 `[DevOps]` CI/CD con GitHub Actions: test → build Docker → deploy en push a `main`
- [ ] 🟢 Testing de carga: subir 50+ PDFs simultáneos y verificar que Celery distribuye correctamente
- [x] 🟢 Verificar que la URL `https://iafacturas.dewoc.com` carga correctamente con SSL activo ✅

---

## Resumen de Avance

| Fase | Descripción | Tareas | Completadas |
|------|-------------|--------|-------------|
| 1 | Producto y Hosting | 6 | 4 |
| 2 | Arquitectura y Setup | 7 | 7 ✅ |
| 3 | DB y Migraciones | 7 | 7 ✅ |
| 4 | OCR, Regex y Extracción | 7 | 7 ✅ |
| 5 | Consulta CAE AFIP | 6 | 0 |
| 6 | Frontend Jinja2 + Bootstrap | 8 | 8 ✅ |
| 7 | Auth, Planes y Pagos | 7 | 4 |
| 8 | Deploy Producción | 9 | 5 |
| **Total** | | **57** | **42** |

---

*Generado el 23 de Abril de 2026 — Dewoc · IAFacturas*
*Actualizado el 24 de Abril de 2026 — Fases 3, 4 y 6 completadas. Fase 7 parcialmente completada (auth + plan limit + planes page).*
