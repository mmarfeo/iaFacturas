"""
Extracción de campos mediante expresiones regulares.

Soporta:
  - Facturas electrónicas AFIP A, B, C, M
  - Notas de crédito / débito
  - Transferencias bancarias (CBU, banco, montos, nombres)

La función principal es extraer_campos(texto, tipo) donde tipo
viene del document_classifier y permite aplicar extractores específicos.
"""
import re
from datetime import date, datetime
from decimal import Decimal, InvalidOperation
from typing import Optional, List


# ═══════════════════════════════════════════════════════════
# PATRONES COMPILADOS — comunes a todos los documentos
# ═══════════════════════════════════════════════════════════

_CUIT      = re.compile(r'\b(\d{2}[-\s]?\d{8}[-\s]?\d)\b')
_CAE       = re.compile(r'C\.?A\.?E\.?[:\s]+(?:N[°º\.\s]+)?(\d{14})', re.IGNORECASE)
_CAE_VENC  = re.compile(
    r'(?:Vto\.?\s+(?:de\s+)?C\.?A\.?E\.?|Vencimiento\s+C\.?A\.?E\.?|'
    r'Fecha\s+de\s+Vto\.?\s+(?:de\s+)?C\.?A\.?E\.?)[:\s]*(\d{2}/\d{2}/\d{4})',
    re.IGNORECASE,
)
_FECHA_RE  = r'\d{1,2}[/\-\.]\d{1,2}[/\-\.]\d{2,4}'


# ═══════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════

def _first(pattern: str, text: str, flags=re.I | re.S) -> Optional[str]:
    m = re.search(pattern, text, flags)
    return m.group(1).strip() if m else None


def _parse_importe(s: str) -> Optional[Decimal]:
    """Convierte '1.234,56' (formato argentino) a Decimal."""
    s = s.strip().replace(" ", "")
    if "," in s and "." in s:
        s = s.replace(".", "").replace(",", ".")
    elif "," in s:
        s = s.replace(",", ".")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _parse_fecha(s: str) -> Optional[date]:
    s = s.strip()
    for fmt in ("%d/%m/%Y", "%d-%m-%Y", "%d.%m.%Y",
                "%d/%m/%y", "%d-%m-%y", "%d.%m.%y"):
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            pass
    return None


def _normalizar_cuit(raw: str) -> str:
    digits = re.sub(r"\D", "", raw)
    if len(digits) == 11:
        return f"{digits[:2]}-{digits[2:10]}-{digits[10]}"
    return raw.strip()


# ═══════════════════════════════════════════════════════════
# SEPARAR SECCIÓN EMISOR / RECEPTOR
# ═══════════════════════════════════════════════════════════

def _split_emisor_receptor(texto: str) -> tuple[str, str]:
    """
    Divide el texto de la factura en sección emisor (parte superior)
    y sección receptor (parte inferior).

    Estrategia 1: palabras clave que marcan datos del receptor.
    Estrategia 2: segundo bloque CUIT como separador.
    """
    m = re.search(
        r'Se[ñn]ores?\s*:'
        r'|Apellido\s+y\s+Nombre.{0,60}[Rr]eceptor'
        r'|Datos\s+del\s+[Rr]eceptor'
        r'|CUIT\s+del\s+[Rr]eceptor'
        r'|Raz[oó]n\s+[Ss]ocial\s+del\s+[Rr]eceptor',
        texto, re.I
    )
    if m:
        return texto[:m.start()], texto[m.start():]

    cuits = list(re.finditer(r'C\.?U\.?I\.?T\.?\s*:?\s*[\d\-]{11,13}', texto, re.I))
    if len(cuits) >= 2:
        return texto[:cuits[1].start()], texto[cuits[1].start():]

    return texto, ""


# ═══════════════════════════════════════════════════════════
# EXTRACCIÓN DE ÍTEMS / DETALLE
# ═══════════════════════════════════════════════════════════

def _extraer_items(texto: str) -> Optional[List[str]]:
    """
    Extrae líneas de ítems/detalle de una factura AFIP.
    Tres estrategias en orden de prioridad.
    """
    def _merge(lineas):
        merged = []
        for l in lineas:
            if re.match(r'^(?:Moneda|Tipo\s+de\s+cambio|Cambio|Currency)\s*[:\-]', l, re.I):
                continue
            es_nueva = bool(re.match(r'^[\d"\']', l)) or bool(re.search(r'\d[\d.,]{4,}', l))
            if merged and not es_nueva:
                merged[-1] = merged[-1] + " " + l
            else:
                merged.append(l)
        return merged

    # Estrategia 1: bloque entre encabezado de tabla y totales
    m = re.search(
        r'(?:Descripci[oó]n|Detalle|Producto|Servicio|Concepto|C[oó]digo\s+Producto)\s*[^\n]*\n'
        r'((?:.|\n)+?)'
        r'(?=Subtotal|Neto\s+Gravado|I\.?V\.?A\.?\s*\d|Importe\s+Total|Total\s*[\$:])',
        texto, re.I
    )
    if m:
        bloque = m.group(1)
        lineas = [l.strip() for l in bloque.split("\n") if len(l.strip()) >= 5]
        lineas = [l for l in lineas if not re.match(
            r'^(?:Cantidad|Unidad|Precio\s+Unit|Importe|Bonif|Desc\.?|U\.?\s*M\.?)\s*$', l, re.I
        )]
        lineas = _merge(lineas)
        if lineas:
            return lineas

    # Estrategia 2: líneas con cantidad al inicio y monto al final
    lineas = [
        l.strip() for l in texto.split("\n")
        if re.match(r'^\d+[\s,\.]\s*\S', l.strip())
        and re.search(r'\$?\s*\d[\d.,]{3,}$', l.strip())
        and len(l.strip()) > 10
    ]
    if lineas:
        return lineas

    # Estrategia 3: unidad de medida explícita
    lineas = [
        l.strip() for l in texto.split("\n")
        if re.search(r'\b\d+[,.]\d{2}\s+(?:unidades?|horas?|u\.|mes(?:es)?|d[íi]as?)\b', l, re.I)
        and re.search(r'\d[\d.,]{3,}', l)
        and len(l.strip()) > 15
    ]
    if lineas:
        return lineas

    return None


# ═══════════════════════════════════════════════════════════
# EXTRACTORES POR TIPO DE DOCUMENTO
# ═══════════════════════════════════════════════════════════

def _extraer_factura(texto: str) -> dict:
    """Extrae todos los campos relevantes de una factura AFIP."""
    c: dict = {}
    emisor_txt, receptor_txt = _split_emisor_receptor(texto)

    # CAE
    m = _CAE.search(texto)
    if m:
        c["cae"] = m.group(1)

    # Vencimiento CAE
    m = _CAE_VENC.search(texto)
    if m:
        c["cae_vencimiento"] = _parse_fecha(m.group(1))

    # CUITs (emisor desde sección emisor, receptor desde sección receptor)
    cuits_emisor = _CUIT.findall(emisor_txt)
    if cuits_emisor:
        c["cuit_emisor"] = _normalizar_cuit(cuits_emisor[0])
    else:
        cuits_todos = _CUIT.findall(texto)
        if cuits_todos:
            c["cuit_emisor"] = _normalizar_cuit(cuits_todos[0])

    if receptor_txt:
        cuits_receptor = _CUIT.findall(receptor_txt)
        if cuits_receptor:
            c["cuit_receptor"] = _normalizar_cuit(cuits_receptor[0])
    if "cuit_receptor" not in c:
        cuits_todos = list(dict.fromkeys(_normalizar_cuit(x) for x in _CUIT.findall(texto)))
        if len(cuits_todos) >= 2:
            c["cuit_receptor"] = cuits_todos[1]

    # Tipo de comprobante
    tipo = _extraer_tipo_comprobante(texto)
    if tipo:
        c["tipo_comprobante"] = tipo

    # Número de comprobante AFIP (XXXX-XXXXXXXX)
    nro = _extraer_numero_comprobante(texto)
    if nro:
        parts = nro.split("-")
        c["punto_venta"] = parts[0]
        c["numero"]      = parts[1] if len(parts) > 1 else nro

    # Fecha de emisión
    v = _first(
        r'[Ff]echa\s+(?:de\s+)?[Ee]mis[ií]?[oó]n\s*:?\s*(' + _FECHA_RE + r')', texto
    ) or _first(
        r'[Ff]echa\s+[Cc]omprobante\s*:?\s*(' + _FECHA_RE + r')', texto
    )
    if v:
        c["fecha_emision"] = _parse_fecha(v)

    # Fecha vencimiento (de la factura, no del CAE)
    v = _first(r'[Vv]encimiento\s*:?\s*(' + _FECHA_RE + r')', texto)
    if v:
        c["fecha_vencimiento"] = _parse_fecha(v)

    # Importe total
    v = _first(r'[Ii]mporte\s+[Tt]otal\s*:?\s*\$?\s*([\d.,]+)', texto) or \
        _first(r'[Tt]otal\s+a\s+[Pp]agar\s*:?\s*\$?\s*([\d.,]+)', texto) or \
        _first(r'[Tt]otal\s*:?\s*\$?\s*([\d.,]+)', texto)
    if v:
        c["importe_total"] = _parse_importe(v)

    # Neto gravado / base imponible
    v = _first(r'[Nn]eto\s+[Gg]ravado\s*:?\s*\$?\s*([\d.,]+)', texto) or \
        _first(r'[Bb]ase\s+[Ii]mponible\s*:?\s*\$?\s*([\d.,]+)', texto) or \
        _first(r'[Ss]ubtotal\s*:?\s*\$?\s*([\d.,]+)', texto)
    if v:
        c["importe_neto"] = _parse_importe(v)

    # IVA 21%
    v = _first(r'I\.?V\.?A\.?\s*21\s*%?\s*:?\s*\$?\s*([\d.,]+)', texto)
    if v:
        c["iva_21"] = _parse_importe(v)

    # Porcentaje IVA genérico
    v = _first(r'IVA\s+(\d+(?:[,.]\d+)?)\s*%', texto)
    if v:
        c["iva_porcentaje"] = v

    # Razón social emisor
    v = _first(
        r'(?:Apellido\s+y\s+Nombre\s*/?\s*Raz[oó]n\s+\w+|Raz[oó]n\s+\w+)\s*:?\s*'
        r'([^\n]{3,80}?)(?:\s+Fecha\s+de|\n|C\.?U\.?I\.?T|$)',
        emisor_txt or texto
    )
    if v:
        c["razon_social_emisor"] = v

    # Razón social receptor
    v = _first(r'Se[ñn]ores?\s*:?\s*([^\n]{3,80}?)(?:\n|C\.?U\.?I\.?T|$)', texto) or \
        _first(
            r'(?:Apellido\s+y\s+Nombre\s*/?\s*Raz[oó]n\s+[Ss]ocial|Raz[oó]n\s+[Ss]ocial)\s*:?\s*'
            r'([^\n]{3,80}?)(?:\n|C\.?U\.?I\.?T|$)',
            receptor_txt
        ) if receptor_txt else None
    if v:
        c["razon_social_receptor"] = v

    # Condición IVA emisor
    v = _first(
        r'(?:Condici[oó]n\s+(?:frente\s+al\s+)?I\.?V\.?A\.?|Categor[ií]a\s+I\.?V\.?A\.?)[:\s]*(.+?)(?:\n)',
        texto
    )
    if v:
        c["condicion_iva_emisor"] = v

    # Condición de venta
    v = _first(r'[Cc]ondici[oó]n\s+(?:de\s+)?[Vv]enta\s*:?\s*([^\n]+)', texto)
    if v:
        c["condicion_venta"] = v

    # Concepto
    v = _first(r'[Cc]oncepto\s*:?\s*(.+?)(?:\n)', texto)
    if v:
        c["concepto"] = v

    # Ítems / Detalle
    items = _extraer_items(texto)
    if items:
        c["items"] = items

    # Observaciones
    v = _first(r'OBSERVACIONES\s*:?\s*(.+?)(?:\n\n|\Z)', texto, re.S | re.I)
    if v:
        c["observaciones"] = v

    return c


def _extraer_transferencia(texto: str) -> dict:
    """Extrae campos de un comprobante de transferencia bancaria."""
    c: dict = {}

    # Importe
    v = _first(r'[Ii]mporte\s*:?\s*\$?\s*([\d.,]+)', texto) or \
        _first(r'[Mm]onto\s*:?\s*\$?\s*([\d.,]+)', texto) or \
        _first(r'\$\s*([\d]{1,3}(?:[.,]\d{3})*(?:[.,]\d{2})?)', texto)
    if v:
        c["importe"] = _parse_importe(v)

    # Fecha de ejecución
    v = _first(r'[Ff]echa\s+(?:de\s+)?[Ee]jecuci[oó]n\s*:?\s*(' + _FECHA_RE + r')', texto) or \
        _first(r'[Ff]echa\s+(?:de\s+la\s+)?[Oo]peraci[oó]n\s*:?\s*(' + _FECHA_RE + r')', texto) or \
        _first(r'[Ff]echa\s*:?\s*(' + _FECHA_RE + r')', texto)
    if v:
        c["fecha_ejecucion"] = _parse_fecha(v)

    # CBU / CVU receptor (último CBU de 22 dígitos = destino)
    cbus = list(re.finditer(r'\b(\d{22})\b', texto))
    if cbus:
        c["cbu_receptor"] = cbus[-1].group(1)
        if len(cbus) >= 2:
            c["cbu_emisor"] = cbus[0].group(1)

    # CUIT / CUIL
    v = _first(r'CUIT\s+o\s+CUIL\s*\n?\s*([\d\-]{11,13})', texto) or \
        _first(r'CUIL\s*:?\s*([\d\-]{11,13})', texto) or \
        _first(r'CUIT\s*:?\s*([\d\-]{11,13})', texto)
    if v:
        c["cuit_receptor"] = _normalizar_cuit(v)

    # Nombre receptor
    v = _first(r'[Dd]estinatario\s*:?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Bb]eneficiario\s*:?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Nn]ombre\s+o\s+raz[oó]n\s+social\s*\n?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Aa]\s+nombre\s+de\s*:?\s*(.+?)(?:\n|$)', texto)
    if v:
        c["nombre_receptor"] = v

    # Nombre emisor
    v = _first(r'[Oo]rdenante\s*:?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Ee]misor\s*:?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Dd]e\s*:\s*([A-ZÁÉÍÓÚÑ][a-záéíóúñ]+ +[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)', texto)
    if v:
        c["nombre_emisor"] = v

    # Número de comprobante / ID transacción
    v = _first(r'[Nn][uú]mero\s+de\s+comprobante\s*\n?\s*([\w\-]+)', texto) or \
        _first(r'[Tt]ransacci[oó]n\s*(?:N[°º]?|#|ID)?\s*:?\s*([\w\-]+)', texto) or \
        _first(r'[Cc]omprobante\s+N[°º]?\s*:?\s*([\w\-]+)', texto) or \
        _first(r'\bID\s*:?\s*([\w\-]{6,})', texto)
    if v:
        c["numero_comprobante"] = v

    # Concepto / descripción
    v = _first(r'[Cc]oncepto\s*:?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Mm]otivo\s*:?\s*(.+?)(?:\n|$)', texto)
    if v:
        c["concepto"] = v

    # Cuenta de débito
    v = _first(r'[Cc]uenta\s+(?:de\s+)?[Dd][eé]bito\s*:?\s*([\w\-/ ]+?)(?:\n|$)', texto) or \
        _first(r'[Cc]uenta\s+[Oo]rigen\s*:?\s*([\w\-/ ]+?)(?:\n|$)', texto)
    if v:
        c["cuenta_debito"] = v

    # Estado
    v = _first(r'[Ee]stado\s*:?\s*(.+?)(?:\n|$)', texto) or \
        _first(r'[Rr]esultado\s*:?\s*(.+?)(?:\n|$)', texto)
    if v:
        c["estado"] = v

    return c


def _extraer_tipo_comprobante(texto: str) -> Optional[str]:
    # Formato explícito: "FACTURA A/B/C"
    m = re.search(r'\bFACTURA\s+(A|B|C|M)\b', texto, re.I)
    if m:
        return f"Factura {m.group(1).upper()}"
    # Layout AFIP dos columnas: letra sola + "FACTURA" abajo
    m = re.search(r'\b(A|B|C|M)\s*\n\s*FACTURA\b', texto, re.I | re.M)
    if m:
        return f"Factura {m.group(1).upper()}"
    # Letra sola en su línea
    m = re.search(r'^\s*(A|B|C|M)\s*$', texto, re.I | re.M)
    if m:
        return f"Factura {m.group(1).upper()}"
    # Nota de crédito / débito
    if re.search(r'nota\s+de\s+cr[eé]dito', texto, re.I):
        return "Nota de Crédito"
    if re.search(r'nota\s+de\s+d[eé]bito', texto, re.I):
        return "Nota de Débito"
    return None


def _extraer_numero_comprobante(texto: str) -> Optional[str]:
    # "Punto de Venta: 0001  Comp. Nro.: 00000282"
    m = re.search(
        r'(?:Punto\s+de\s+[Vv]enta|P\.?\s*V\.?)\s*:?\s*(\d{1,5})'
        r'\s+(?:Comp\.?\s*Nro\.?|N[°º]?)\s*:?\s*(\d{1,8})',
        texto, re.I
    )
    if m:
        return f"{m.group(1).zfill(4)}-{m.group(2).zfill(8)}"
    # Formato unificado XXXX-XXXXXXXX
    m = re.search(r'\b(\d{4,5})[-](\d{6,8})\b', texto)
    if m:
        return f"{m.group(1)}-{m.group(2)}"
    return None


# ═══════════════════════════════════════════════════════════
# FUNCIÓN PRINCIPAL
# ═══════════════════════════════════════════════════════════

def extraer_campos(texto: str, tipo: str = "factura_a") -> dict:
    """
    Extrae campos del documento según su tipo.

    Retorna dict con campos encontrados más metadatos:
      _confidence  float 0-1  (fracción de campos clave encontrados)
      _texto_len   int        (longitud del texto)
      _tipo        str        (tipo de documento)
    """
    from app.services.document_classifier import es_transferencia

    if es_transferencia(tipo):
        campos = _extraer_transferencia(texto)
        clave  = ["importe", "fecha_ejecucion", "cbu_receptor"]
    else:
        campos = _extraer_factura(texto)
        clave  = ["cae", "cuit_emisor", "importe_total", "fecha_emision"]

    campos["_confidence"] = sum(1 for k in clave if k in campos) / len(clave)
    campos["_texto_len"]  = len(texto)
    campos["_tipo"]       = tipo

    return campos
