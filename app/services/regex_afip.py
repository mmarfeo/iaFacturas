"""
Extracción de campos AFIP mediante expresiones regulares.
Cubre facturas electrónicas A, B, C y M emitidas por cualquier contribuyente.
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional

# ──────────────────────────────────────────────────────────
# Patrones compilados
# ──────────────────────────────────────────────────────────

_CUIT = re.compile(r'\b(\d{2}[-\s]?\d{8}[-\s]?\d)\b')

_CAE = re.compile(
    r'C\.?A\.?E\.?[:\s]+(?:N[°º\.\s]+)?(\d{14})',
    re.IGNORECASE,
)
_CAE_VENC = re.compile(
    r'(?:Vto\.?\s+(?:de\s+)?C\.?A\.?E\.?|Vencimiento\s+C\.?A\.?E\.?|'
    r'Fecha\s+de\s+Vto\.?\s+(?:de\s+)?C\.?A\.?E\.?)[:\s]*(\d{2}/\d{2}/\d{4})',
    re.IGNORECASE,
)
_TIPO_COMP = re.compile(
    r'((?:FACTURA|NOTA\s+DE\s+(?:CR[EÉ]DITO|D[EÉ]BITO)|RECIBO|LIQUIDACI[OÓ]N)\s+[ABCMX])',
    re.IGNORECASE,
)
_NRO_COMP = re.compile(r'\b(\d{4})[-\s]+(\d{8})\b')
_FECHA_EMISION = re.compile(
    r'(?:Fecha\s+(?:de\s+)?[Ee]mis[ií]?[oó]n|Fecha\s+[Cc]omprobante|'
    r'Fecha\s+[Ff]actura)[:\s]*(\d{2}/\d{2}/\d{4})',
    re.IGNORECASE,
)
_IMPORTE_TOTAL = re.compile(
    r'(?:Importe\s+Total|Total\s+a\s+Pagar|Total)[:\s]*\$?\s*([\d.,]+)',
    re.IGNORECASE,
)
_NETO = re.compile(
    r'(?:Neto\s+Gravado|Importe\s+Neto\s+Gravado|Base\s+Imponible)[:\s]*\$?\s*([\d.,]+)',
    re.IGNORECASE,
)
_IVA_21 = re.compile(
    r'(?:I\.?V\.?A\.?\s*21\s*%|IVA\s+21)[:\s]*\$?\s*([\d.,]+)',
    re.IGNORECASE,
)
_RAZON_SOCIAL = re.compile(
    r'(?:Raz[oó]n\s+Social|Apellido\s+y\s+Nombre|Nombre\s+y\s+Apellido)[:\s]*(.+?)(?:\n|CUIT)',
    re.IGNORECASE,
)
_CONDICION_IVA = re.compile(
    r'(?:Condici[oó]n\s+(?:frente\s+al\s+)?I\.?V\.?A\.?|Categor[ií]a\s+I\.?V\.?A\.?)[:\s]*(.+?)(?:\n)',
    re.IGNORECASE,
)
_CONCEPTO = re.compile(
    r'(?:Concepto)[:\s]*(.+?)(?:\n)',
    re.IGNORECASE,
)


# ──────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────

def _parse_importe(s: str) -> Optional[Decimal]:
    """Convierte '1.234,56' (formato argentino) a Decimal."""
    s = s.strip().replace(' ', '')
    if ',' in s and '.' in s:
        # 1.234,56 → 1234.56
        s = s.replace('.', '').replace(',', '.')
    elif ',' in s:
        s = s.replace(',', '.')
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_fecha(s: str) -> Optional[date]:
    try:
        return datetime.strptime(s.strip(), '%d/%m/%Y').date()
    except ValueError:
        return None


def _normalizar_cuit(raw: str) -> str:
    digits = re.sub(r'\D', '', raw)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
    return raw.strip()


# ──────────────────────────────────────────────────────────
# Función principal
# ──────────────────────────────────────────────────────────

def extraer_campos(texto: str) -> dict:
    """
    Extrae todos los campos AFIP relevantes de `texto`.

    Retorna un dict con los campos encontrados más:
      _confidence  float 0-1  (fracción de campos clave encontrados)
      _texto_len   int        (longitud del texto procesado)
    """
    c: dict = {}

    # CAE
    m = _CAE.search(texto)
    if m:
        c['cae'] = m.group(1)

    # Vencimiento CAE
    m = _CAE_VENC.search(texto)
    if m:
        c['cae_vencimiento'] = _parse_fecha(m.group(1))

    # CUITs (emisor = primero, receptor = segundo)
    cuits_raw = _CUIT.findall(texto)
    cuits = list(dict.fromkeys(_normalizar_cuit(x) for x in cuits_raw))
    if cuits:
        c['cuit_emisor'] = cuits[0]
    if len(cuits) > 1:
        c['cuit_receptor'] = cuits[1]

    # Tipo de comprobante
    m = _TIPO_COMP.search(texto)
    if m:
        c['tipo_comprobante'] = m.group(1).strip().title()

    # Número (punto de venta + número)
    m = _NRO_COMP.search(texto)
    if m:
        c['punto_venta'] = m.group(1)
        c['numero'] = m.group(2)

    # Fecha de emisión
    m = _FECHA_EMISION.search(texto)
    if m:
        c['fecha_emision'] = _parse_fecha(m.group(1))

    # Importes
    m = _IMPORTE_TOTAL.search(texto)
    if m:
        c['importe_total'] = _parse_importe(m.group(1))

    m = _NETO.search(texto)
    if m:
        c['importe_neto'] = _parse_importe(m.group(1))

    m = _IVA_21.search(texto)
    if m:
        c['iva_21'] = _parse_importe(m.group(1))

    # Razón social emisor
    m = _RAZON_SOCIAL.search(texto)
    if m:
        c['razon_social_emisor'] = m.group(1).strip()

    # Condición IVA emisor
    m = _CONDICION_IVA.search(texto)
    if m:
        c['condicion_iva_emisor'] = m.group(1).strip()

    # Concepto
    m = _CONCEPTO.search(texto)
    if m:
        c['concepto'] = m.group(1).strip()

    # Confidence: fracción de 4 campos clave encontrados
    clave = ['cae', 'cuit_emisor', 'importe_total', 'fecha_emision']
    c['_confidence'] = sum(1 for k in clave if k in c) / len(clave)
    c['_texto_len'] = len(texto)

    return c
