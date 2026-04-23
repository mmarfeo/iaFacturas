from celery import Celery
from app.core.config import settings

celery_app = Celery(
    "iafacturas",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=["tasks.procesar_factura"],
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="America/Argentina/Buenos_Aires",
    enable_utc=True,
    task_routes={
        "tasks.procesar_factura.*": {"queue": "facturas"},
    },
    task_soft_time_limit=180,  # 3 min — si OCR tarda demasiado
    task_time_limit=240,
)
