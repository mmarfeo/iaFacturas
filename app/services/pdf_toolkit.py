"""
PDF Toolkit: separa hojas de PDFs y empaqueta en ZIP (en memoria).
Basado en pdf_toolkit_hojas.py (CLI). Usa pypdfium2.
"""
from __future__ import annotations

import io
import re
import zipfile

import pypdfium2 as pdfium


def normalizar_stem(nombre: str) -> str:
    """Nombre base seguro para archivos."""
    nombre = nombre.strip()
    nombre = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", nombre)
    nombre = re.sub(r"\s+", " ", nombre).strip()
    return nombre or "documento"


def _stem_unico(stem: str, usados: set[str]) -> str:
    base = normalizar_stem(stem)
    candidato = base
    n = 2
    while candidato in usados:
        candidato = f"{base}__{n}"
        n += 1
    usados.add(candidato)
    return candidato


def _rango_hojas(total: int, mode: str, start_1: int, end_1: int) -> list[int]:
    if total <= 0:
        raise ValueError("El PDF no tiene páginas.")
    if mode == "all":
        return list(range(total))
    s = max(1, start_1)
    e = max(1, end_1)
    if s > e:
        s, e = e, s
    indices = [i for i in range(total) if s <= i + 1 <= e]
    if not indices:
        raise ValueError(
            f"El rango {s}–{e} no incluye ninguna página válida "
            f"(el documento tiene {total} página(s))."
        )
    return indices


def separar_pdfs_en_zip(
    archivos: list[tuple[str, bytes]],
    mode: str,
    page_start: int,
    page_end: int,
) -> tuple[bytes, int]:
    """
    Separa las páginas de uno o varios PDFs y devuelve (zip_bytes, total_páginas_generadas).

    archivos: lista de (nombre_archivo, contenido_bytes)
    mode: "all" | "range"
    page_start / page_end: 1-based, sólo se usan en modo "range"
    """
    zip_buf = io.BytesIO()
    total_paginas = 0
    usados: set[str] = set()

    with zipfile.ZipFile(zip_buf, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for nombre, pdf_bytes in archivos:
            stem_base = nombre.rsplit(".", 1)[0] if "." in nombre else nombre
            stem = _stem_unico(stem_base, usados)

            with pdfium.PdfDocument(pdf_bytes) as src:
                n = len(src)
                indices = _rango_hojas(n, mode, page_start, page_end)

                for i in indices:
                    num_hoja = i + 1
                    out_name = f"{stem}_num_hoja_{num_hoja}.pdf"

                    with pdfium.PdfDocument.new() as dst:
                        dst.import_pages(src, [i])
                        page_buf = io.BytesIO()
                        dst.save(page_buf)
                        zf.writestr(out_name, page_buf.getvalue())

                    total_paginas += 1

    return zip_buf.getvalue(), total_paginas


def contar_paginas(pdf_bytes: bytes) -> int:
    """Devuelve la cantidad de páginas de un PDF en bytes."""
    with pdfium.PdfDocument(pdf_bytes) as doc:
        return len(doc)
