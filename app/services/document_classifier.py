"""
Clasificación de documentos argentinos.

Retorna: (tipo: str, confianza: float)

Tipos soportados:
  factura_a, factura_b, factura_c
  nota_credito, nota_debito
  remito, recibo
  transferencia_santander, transferencia_galicia, transferencia_bbva,
  transferencia_bna, transferencia_macro, transferencia_provincia,
  transferencia_mercadopago, transferencia_brubank, transferencia_naranja,
  transferencia_uala, transferencia_bind, transferencia_otro
  desconocido
"""
import re


def clasificar_documento(texto: str) -> tuple[str, float]:
    """
    Clasifica el tipo de documento a partir del texto extraído.
    Retorna (tipo, confianza) donde confianza está en [0.0, 1.0].
    """
    if not texto or not texto.strip():
        return "desconocido", 0.0

    t = texto.lower()

    # ── Transferencias bancarias ────────────────────────────────────────────
    _kw_transferencia = (
        "comprobante de transferencia",
        "comprobante de pago",
        "constancia de transferencia",
        "transferencia realizada",
        "transferencia enviada",
        "transferencia exitosa",
        "transferencia acreditada",
        "transferencia inmediata",
        "operación realizada",
        "operacion realizada",
        "confirmación de transferencia",
        "confirmacion de transferencia",
        "débito inmediato",
        "debito inmediato",
        "debin",
        "echeq",
        "monto transferido",
        "importe transferido",
        "cuenta de origen",
        "cuenta origen",
    )
    _es_transferencia = any(kw in t for kw in _kw_transferencia)
    _tiene_cbu = bool(re.search(r'\b\d{22}\b', texto))

    if _es_transferencia or _tiene_cbu:
        tipo = _detectar_banco(t)
        conf = 0.90 if _tiene_cbu else 0.80
        return tipo, conf

    # ── Facturas AFIP ───────────────────────────────────────────────────────
    if re.search(r'\bfactura\b', t):
        if re.search(r'cod\.?\s*0*1\b|tipo\s+a\b|\bfactura\s+a\b', t):
            return "factura_a", 0.92
        if re.search(r'cod\.?\s*0*6\b|cod\.?\s*006\b|\bfactura\s+b\b|tipo\s+b\b', t):
            return "factura_b", 0.92
        if re.search(r'cod\.?\s*0*11\b|cod\.?\s*011\b|\bfactura\s+c\b|monotributo', t):
            return "factura_c", 0.90
        # Factura sin tipo claro pero con CAE → alta probabilidad
        if re.search(r'\bcae\b', t):
            return "factura_a", 0.70
        return "factura_a", 0.60  # Asumir A por defecto cuando dice "factura"

    # ── Otros comprobantes AFIP ─────────────────────────────────────────────
    if "nota de credito" in t or "nota de crédito" in t:
        return "nota_credito", 0.90
    if "nota de debito" in t or "nota de débito" in t:
        return "nota_debito", 0.90
    if re.search(r'\bremito\b', t):
        return "remito", 0.85
    if re.search(r'\brecibo\b', t):
        return "recibo", 0.80

    # ── Señales débiles: CUIT + CAE pero sin "factura" explícito ───────────
    tiene_cuit = bool(re.search(r'\b\d{2}[-\s]?\d{8}[-\s]?\d\b', texto))
    tiene_cae  = bool(re.search(r'\bcae\b', t))
    if tiene_cuit and tiene_cae:
        return "factura_a", 0.55

    return "desconocido", 0.30


def _detectar_banco(t: str) -> str:
    if "santander" in t:
        return "transferencia_santander"
    if "galicia" in t:
        return "transferencia_galicia"
    if "bbva" in t or "frances" in t or "francés" in t:
        return "transferencia_bbva"
    if "nacion" in t or "nación" in t or "bna" in t:
        return "transferencia_bna"
    if "macro" in t:
        return "transferencia_macro"
    if "provincia" in t or "bapro" in t:
        return "transferencia_provincia"
    if "mercado pago" in t or "mercadopago" in t:
        return "transferencia_mercadopago"
    if "brubank" in t:
        return "transferencia_brubank"
    if "naranja" in t:
        return "transferencia_naranja"
    if "uala" in t or "ualá" in t:
        return "transferencia_uala"
    if "bind" in t:
        return "transferencia_bind"
    return "transferencia_otro"


def es_factura(tipo: str) -> bool:
    return tipo.startswith("factura") or tipo in ("nota_credito", "nota_debito")


def es_transferencia(tipo: str) -> bool:
    return tipo.startswith("transferencia")
