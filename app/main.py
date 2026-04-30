from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from app.core.config import settings
from app.core.database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # En producción las tablas se crean con Alembic; esto es útil en dev
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    yield


app = FastAPI(
    title="IAFacturas API",
    description="Extracción y validación de facturas AFIP con IA",
    version="1.0.0",
    docs_url="/api/docs" if settings.is_dev else None,
    redoc_url="/api/redoc" if settings.is_dev else None,
    lifespan=lifespan,
)

# ── Static files ──────────────────────────────────────────────────────────────
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# ── Routers ───────────────────────────────────────────────────────────────────
from app.routers import auth, facturas, cae, api_publica, lotes, pdf_toolkit, invoice_templates, feedback, admin_usuarios, ayuda  # noqa: E402

app.include_router(auth.router)
app.include_router(facturas.router)
app.include_router(cae.router)
app.include_router(api_publica.router)
app.include_router(lotes.router)
app.include_router(pdf_toolkit.router)
app.include_router(invoice_templates.router)
app.include_router(feedback.router)
app.include_router(admin_usuarios.router)
app.include_router(ayuda.router)


# ── Health check ──────────────────────────────────────────────────────────────
@app.get("/health", tags=["Sistema"])
async def health():
    return {"status": "ok", "app": "IAFacturas", "version": "1.0.0"}
