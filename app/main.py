from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from contextlib import asynccontextmanager

from app.core.config import settings
from app.core.database import engine, Base


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Crear tablas al arrancar (en producción usar Alembic)
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

# Static files y templates
app.mount("/static", StaticFiles(directory="app/static"), name="static")
templates = Jinja2Templates(directory="app/templates")


# ── Routers (se irán agregando por fase) ─────────────────────────────────────

# from app.routers import facturas, cae, auth, planes
# app.include_router(facturas.router, prefix="/facturas", tags=["Facturas"])
# app.include_router(cae.router, prefix="/cae", tags=["CAE AFIP"])
# app.include_router(planes.router, prefix="/planes", tags=["Planes"])


@app.get("/health")
async def health():
    return {"status": "ok", "app": "IAFacturas", "version": "1.0.0"}


@app.get("/")
async def landing(request):
    from fastapi import Request
    return templates.TemplateResponse("landing.html", {"request": request})
