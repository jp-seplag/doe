"""
Extração de texto do PDF do DOE-PE com suporte a layout multi-coluna.

O DOE-PE usa tipicamente 2-3 colunas por página. Usamos pdfplumber com
layout=True (PDFMiner LAParams) para reconstrução automática de colunas,
seguido de limpeza de artefatos comuns de extração de PDF.
"""

import re
import pdfplumber
from pathlib import Path
from typing import List, Dict


def extract_pages(pdf_path: str | Path) -> List[Dict]:
    """
    Extrai texto de cada página, respeitando o layout de colunas.
    Retorna lista de dicts com número da página e texto limpo.
    """
    result = []
    with pdfplumber.open(str(pdf_path)) as pdf:
        total = len(pdf.pages)
        for i, page in enumerate(pdf.pages):
            text = _extract_page_text(page)
            result.append({
                "page_num": i + 1,
                "total_pages": total,
                "text": text,
            })
    return result


def _extract_page_text(page) -> str:
    """
    Tenta extração com layout=True (colunas automáticas).
    Se falhar ou retornar muito pouco, usa fallback por bounding boxes.
    """
    try:
        text = page.extract_text(layout=True, x_tolerance=3, y_tolerance=3) or ""
        text = _clean(text)
        if len(text) > 100:
            return text
    except Exception:
        pass

    # Fallback: detecção manual de colunas por clusters de x0
    return _extract_by_columns(page)


def _extract_by_columns(page) -> str:
    """Detecta colunas pela distribuição de x0 das palavras e extrai em ordem."""
    words = page.extract_words(x_tolerance=3, y_tolerance=3, keep_blank_chars=False)
    if not words:
        return ""

    pw = page.width
    margin_l = pw * 0.05
    margin_r = pw * 0.95

    # Histograma de x0 em bins de 1% da largura da página
    bin_size = pw * 0.01
    n_bins = int((margin_r - margin_l) / bin_size) + 1
    hist = [0] * n_bins
    for w in words:
        b = int((w["x0"] - margin_l) / bin_size)
        if 0 <= b < n_bins:
            hist[b] += 1

    # Detecta vales (gutters) — regiões com poucos caracteres
    gutters = _find_gutters(hist, bin_size, margin_l, pw)

    if not gutters:
        return _clean(page.extract_text() or "")

    # Constrói faixas de coluna
    boundaries = [margin_l] + gutters + [margin_r]
    col_ranges = [(boundaries[i], boundaries[i + 1]) for i in range(len(boundaries) - 1)]

    col_texts = []
    for col_l, col_r in col_ranges:
        col_words = [w for w in words if w["x0"] >= col_l - 2 and w["x1"] <= col_r + 2]
        col_texts.append(_words_to_text(col_words))

    return _clean("\n\n".join(t for t in col_texts if t))


def _find_gutters(hist: list, bin_size: float, margin_l: float, page_width: float) -> list:
    """
    Encontra regiões de baixa densidade (gutters entre colunas).
    Retorna lista de x-positions que separam colunas.
    """
    threshold = max(hist) * 0.05  # gutter tem < 5% do pico
    min_gutter_bins = max(1, int(page_width * 0.03 / bin_size))  # pelo menos 3% da largura

    in_gutter = False
    gutter_start = None
    gutters = []

    for i, count in enumerate(hist):
        if count <= threshold:
            if not in_gutter:
                in_gutter = True
                gutter_start = i
        else:
            if in_gutter and (i - gutter_start) >= min_gutter_bins:
                mid = (gutter_start + i) / 2
                gutters.append(margin_l + mid * bin_size)
            in_gutter = False

    return gutters


def _words_to_text(words: list) -> str:
    if not words:
        return ""

    words = sorted(words, key=lambda w: (round(w["top"] / 3) * 3, w["x0"]))
    lines = []
    cur_top = None
    cur_line = []

    for w in words:
        t = round(w["top"] / 3) * 3
        if cur_top is None or abs(t - cur_top) > 4:
            if cur_line:
                lines.append(" ".join(cur_line))
            cur_line = [w["text"]]
            cur_top = t
        else:
            cur_line.append(w["text"])

    if cur_line:
        lines.append(" ".join(cur_line))

    return "\n".join(lines)


def _clean(text: str) -> str:
    """Remove artefatos comuns de extração de PDF."""
    # Remove referências CID (fontes não mapeadas)
    text = re.sub(r"\(cid:\d+\)", "", text)
    # Normaliza espaços horizontais
    text = re.sub(r"[ \t]+", " ", text)
    # Colapsa linhas em branco múltiplas
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def full_text(pages: List[Dict]) -> str:
    """Concatena todas as páginas com separador de página."""
    parts = []
    for p in pages:
        parts.append(f"\n[PÁGINA {p['page_num']}]\n{p['text']}")
    return "\n".join(parts)
