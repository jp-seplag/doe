"""
Segmenta o texto completo do DOE em atos individuais.

Estratégia: encontra todas as âncoras (início de cada ato) via regex,
usa as posições como fronteiras e extrai o texto entre âncoras consecutivas.
"""

import re
from typing import List, Dict

# Meses em português (maiúsculo e com acento)
_MESES = (
    r"JANEIRO|FEVEREIRO|MAR[CÇ]O|ABRIL|MAIO|JUNHO|"
    r"JULHO|AGOSTO|SETEMBRO|OUTUBRO|NOVEMBRO|DEZEMBRO"
)

# (tipo, padrão regex) — ordem importa: mais específico primeiro
_PATTERNS: List[tuple] = [
    # ── Decretos ──────────────────────────────────────────────────────────────
    ("decreto",
     rf"DECRETO\s+N[Oº°]?\s*[\d\.]+\s*,\s*DE\s+\d+\s+DE\s+(?:{_MESES})\s+DE\s+\d{{4}}\."),

    # ── Portarias (vários formatos) ───────────────────────────────────────────
    ("portaria",
     r"PORTARIA\s+[\w/]+\s+N[Oº°]?\s*[\d\./]+(?:\s+(?:DE|DO\s+DIA)\s+\d+)?"),

    # ── Resoluções ────────────────────────────────────────────────────────────
    ("resolucao",
     r"RESOLU[CÇ][AÃ]O\s+[\w/]+\s+N[Oº°]?\s*[\d\.]+"),

    # ── Instruções Normativas / de Serviço ────────────────────────────────────
    ("instrucao_normativa",
     r"INSTRU[CÇ][AÃ]O\s+(?:NORMATIVA|DE\s+SERVI[CÇ]O)\s+[\w/]+\s+N[Oº°]?\s*[\d\.]+"),

    # ── Atos pessoais numerados (Nº XXXX - Nomear/Exonerar...) ───────────────
    # Inclui os formatos do DOE: "Nº 2758 -" e "N° 1.554-"
    ("ato_pessoal",
     r"N[Oº°]\s*[\d\.]+\s*[-–]\s*"
     r"(?:Nomear|Exonerar|Designar|Promover|Afastar|Ceder|Aposentar|Demitir|"
     r"Retornar|Transferir|Incluir|Excluir|Reconhecer|Autorizar|Conceder|"
     r"Tornar\s+sem\s+efeito|Fazer\s+retornar|Considerar|PROMOVER|AGREGAR|"
     r"Defiro|DEFIRO|Instaur)"),

    # ── Decisões tributárias (TATE) ───────────────────────────────────────────
    ("decisao_tributaria",
     r"INTERESSADO:\s+[A-ZÁÉÍÓÚÀÂÊÔÃÕÜ]"),

    # ── Matérias jornalísticas (título em caixa alta, linha própria) ──────────
    # Só detecta se a linha tiver entre 10 e 80 chars e for toda maiúscula
    ("materia",
     r"(?m)^[A-ZÁÉÍÓÚÀÂÊÔÃÕÜ][A-ZÁÉÍÓÚÀÂÊÔÃÕÜ\s\-,]{9,79}$"),
]

_COMPILED = [
    (t, re.compile(p, re.IGNORECASE | re.MULTILINE))
    for t, p in _PATTERNS
]

# Tipos que sobrepõem outros: se houver match de tipo mais específico
# próximo, o tipo genérico (materia) é descartado
_GENERIC_TYPES = {"materia"}


def segment(text: str) -> List[Dict]:
    """
    Divide o texto completo do DOE em segmentos por ato.

    Retorna lista de dicts com:
      - tipo: classificação do ato
      - texto: conteúdo completo do ato
      - posicao: índice de ordem no documento
    """
    markers = _find_markers(text)
    markers = _dedup_markers(markers)
    segments = _build_segments(text, markers)
    return segments


def _find_markers(text: str) -> List[Dict]:
    markers = []
    for act_type, pattern in _COMPILED:
        for m in pattern.finditer(text):
            markers.append({
                "pos": m.start(),
                "end": m.end(),
                "type": act_type,
                "match": m.group()[:80],
            })
    return markers


def _dedup_markers(markers: List[Dict]) -> List[Dict]:
    """
    Remove marcadores sobrepostos, priorizando tipos mais específicos.
    Dois marcadores se sobrepõem se a distância entre eles < 30 chars.
    """
    if not markers:
        return []

    markers.sort(key=lambda x: x["pos"])
    deduped = []
    last_pos = -1
    last_type = None

    for m in markers:
        gap = m["pos"] - last_pos
        if gap < 30:
            # Sobreposto: mantém o mais específico
            if last_type in _GENERIC_TYPES and m["type"] not in _GENERIC_TYPES:
                deduped.pop()  # remove o genérico que entrou antes
            elif m["type"] in _GENERIC_TYPES:
                continue  # ignora o genérico
            else:
                continue  # mantém o primeiro
        deduped.append(m)
        last_pos = m["pos"]
        last_type = m["type"]

    return deduped


def _build_segments(text: str, markers: List[Dict]) -> List[Dict]:
    segments = []
    for i, marker in enumerate(markers):
        start = marker["pos"]
        end = markers[i + 1]["pos"] if i + 1 < len(markers) else len(text)
        raw = text[start:end].strip()

        # Descarta fragmentos muito pequenos (provavelmente ruído)
        if len(raw) < 40:
            continue

        segments.append({
            "tipo": marker["type"],
            "texto": raw,
            "posicao": i,
        })

    return segments
