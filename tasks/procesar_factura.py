"""
Tarea Celery para procesamiento async de facturas en background.
Se llama desde el endpoint POST /facturas/analizar.
"""
from tasks.celery_app import celery_app


@celery_app.task(bind=True, name="tasks.procesar_factura.procesar", max_retries=2)
def procesar_factura(self, factura_id: int, archivo_path: str):
    """
    Pipeline:
    1. pdfplumber → extracción de texto nativo
    2. pytesseract → OCR si el PDF es imagen
    3. regex_afip → extracción de campos AFIP
    4. Ollama/OpenAI (LLM) → fallback si confianza < threshold
    5. afip.py → validación CAE online (con caché Redis)
    6. Guardar resultado en DB (campo datos_extraidos JSONB)
    """
    try:
        # TODO Fase 4: implementar pipeline completo
        # from app.services.ocr import extraer_texto
        # from app.services.regex_afip import extraer_campos
        # from app.services.afip import validar_cae
        # from app.services.llm_extractor import extraer_con_llm
        print(f"[Celery] Procesando factura {factura_id}: {archivo_path}")
        return {"factura_id": factura_id, "estado": "pendiente_implementacion"}

    except Exception as exc:
        raise self.retry(exc=exc, countdown=30)
