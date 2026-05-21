"""
Extrai campos estruturados de cada tipo de ato.

Cada função parse_* recebe o texto bruto do ato e retorna um dict
com os campos extraídos. Campos ausentes são omitidos (não retorna None).
"""

import re
from datetime import date
from typing import Dict, Optional

_MESES = {
    "JANEIRO": 1, "FEVEREIRO": 2, "MARÇO": 3, "MARCO": 3, "ABRIL": 4,
    "MAIO": 5, "JUNHO": 6, "JULHO": 7, "AGOSTO": 8,
    "SETEMBRO": 9, "OUTUBRO": 10, "NOVEMBRO": 11, "DEZEMBRO": 12,
}


def _parse_date_extenso(day_str: str, month_str: str, year_str: str) -> Optional[date]:
    try:
        mes = _MESES.get(month_str.upper().strip())
        if mes:
            return date(int(year_str), mes, int(day_str))
    except (ValueError, TypeError):
        pass
    return None


def _parse_date_numerico(day_str: str, month_str: str, year_str: str) -> Optional[date]:
    try:
        return date(int(year_str), int(month_str), int(day_str))
    except (ValueError, TypeError):
        return None


def _parse_valor(valor_str: str) -> Optional[float]:
    """Converte "20.402.602,16" para float."""
    try:
        return float(valor_str.replace(".", "").replace(",", "."))
    except (ValueError, AttributeError):
        return None


# ── Decreto ──────────────────────────────────────────────────────────────────

def parse_decreto(text: str) -> Dict:
    result: Dict = {}

    # Número e data do decreto
    m = re.search(
        r"DECRETO\s+N[Oº°]?\s*([\d\.]+)\s*,\s*DE\s+(\d+)\s+DE\s+(\w+)\s+DE\s+(\d{4})",
        text, re.IGNORECASE
    )
    if m:
        result["numero"] = m.group(1)
        d = _parse_date_extenso(m.group(2), m.group(3), m.group(4))
        if d:
            result["data_ato"] = d

    # Ementa: linha após cabeçalho que pareça uma ementa de decreto.
    # Ementas tipicamente começam com verbo no infinitivo ou substantivo e
    # têm entre 15 e 180 chars. Evitamos linhas de cabeçalho, assinaturas e
    # texto de artigo (começa com "Art." ou "A GOVERNADORA").
    _SKIP = re.compile(
        r"^(A\s+GOVERNADORA|DECRETO|Art\.|Pal[áa]cio|Recife,|"
        r"Governo\s+do\s+Estado|SECRET[AÁ]R|Governadora|"
        r"\[P[ÁA]G|RAQUEL|T[ÚU]LIO|ANA\s+MAR|RODRIGO|BIANCA|"
        r"ANDREZA|SIMONE|FL[AÁ]VIO|RODRIGO)", re.IGNORECASE
    )
    _EMENTA_VERBS = re.compile(
        r"^(Nomear?|Exoner|Designar?|Transfer|Redenominar?|Aloca?|"
        r"Abrir?|Declara?|Cria?|Institu|Regulamenta?|Altera?|Revogar?|"
        r"Autoriza?|Disp[õo]e|Estabelece?|Prorroga?|Fix[ae]|Aprova?|"
        r"Dispensa?|Concede?|Abre\s|Constitui?|Dá\s|Ratifica?)",
        re.IGNORECASE,
    )
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    # Primeira passagem: procura ementa com verbo típico (mais confiável)
    for line in lines[1:15]:
        if 15 < len(line) < 200 and _EMENTA_VERBS.match(line):
            result["ementa"] = line
            break
    # Segunda passagem: qualquer linha que não seja cabeçalho
    if "ementa" not in result:
        for line in lines[1:10]:
            if 15 < len(line) < 200 and not _SKIP.match(line):
                result["ementa"] = line
                break

    # Crédito suplementar
    m_val = re.search(
        r"cr[eé]dito\s+(?:suplementar|especial|extraordin[aá]rio)\s+no\s+valor\s+de\s+R\$\s*([\d\.,]+)",
        text, re.IGNORECASE
    )
    if m_val:
        result["tipo_credito"] = "suplementar"
        v = _parse_valor(m_val.group(1))
        if v:
            result["valor"] = v

    # Tipo de crédito (especial / extraordinário)
    m_tc = re.search(r"cr[eé]dito\s+(especial|extraordin[aá]rio)", text, re.IGNORECASE)
    if m_tc:
        result["tipo_credito"] = m_tc.group(1).lower()

    # Órgão favorecido
    m_org = re.search(r"em\s+favor\s+d[aoe]\s+(.+?)(?:,\s*cr[eé]dito|\.)", text, re.IGNORECASE)
    if m_org:
        result["orgao_favorecido"] = m_org.group(1).strip()

    # Data retroativa
    m_retro = re.search(
        r"retroagindo\s+seus\s+efeitos\s+a\s+(\d+)[oº°]?\s+de\s+(\w+)\s+de\s+(\d{4})",
        text, re.IGNORECASE
    )
    if m_retro:
        d = _parse_date_extenso(m_retro.group(1), m_retro.group(2), m_retro.group(3))
        if d:
            result["data_retroativa"] = d

    return result


# ── Ato Pessoal ───────────────────────────────────────────────────────────────

_TIPO_ACAO_MAP = {
    "nomear": "nomear",
    "exonerar": "exonerar",
    "designar": "designar",
    "promover": "promover",
    "afastar": "afastar",
    "ceder": "ceder",
    "aposentar": "aposentar",
    "demitir": "demitir",
    "retornar": "retornar",
    "transferir": "transferir",
    "agregar": "agregar",
    "reconhecer": "reconhecer",
    "tornar sem efeito": "tornar_sem_efeito",
    "fazer retornar": "retornar",
    "considerar": "reconhecer",
    "defiro": "deferir",
    "autorizar": "autorizar",
    "conceder": "conceder",
    "instaur": "instaurar",
}


def parse_ato_pessoal(text: str) -> Dict:
    result: Dict = {}

    # Número do ato e tipo de ação
    m = re.search(
        r"N[Oº°]\s*([\d\.]+)\s*[-–]\s*"
        r"(Nomear|Exonerar|Designar|Promover|Afastar|Ceder|Aposentar|Demitir|"
        r"Retornar|Transferir|Incluir|Excluir|Reconhecer|Autorizar|Conceder|"
        r"Tornar\s+sem\s+efeito|Fazer\s+retornar|Considerar|PROMOVER|AGREGAR|"
        r"Defiro|DEFIRO|Instaur)\s+"
        r"([A-ZÁÉÍÓÚÀÂÊÔÃÕÜ][A-ZÁÉÍÓÚÀÂÊÔÃÕÜa-záéíóúàâêôãõü\s]+?)(?=,|\bpara\b|\bdo\b|\bda\b|\bde\b|\bao\b|matr)",
        text, re.IGNORECASE
    )
    if m:
        result["numero_ato"] = m.group(1).replace(".", "")
        acao_raw = m.group(2).lower().strip()
        result["tipo_acao"] = _TIPO_ACAO_MAP.get(acao_raw, acao_raw)
        result["nome"] = " ".join(m.group(3).strip().split())  # normaliza espaços

    # Cargo em comissão
    m_cargo = re.search(
        r"cargo\s+(?:em\s+comiss[aã]o\s+)?(?:de\s+)?([^,]+?)(?:,|\s+s[íi]mbolo|\s+d[aoe]\s+)",
        text, re.IGNORECASE
    )
    if m_cargo:
        result["cargo"] = m_cargo.group(1).strip()

    # Função gratificada
    if "cargo" not in result:
        m_fg = re.search(
            r"Fun[cç][aã]o\s+Gratificada\s+de\s+([^,]+?)(?:,|\s+s[íi]mbolo)",
            text, re.IGNORECASE
        )
        if m_fg:
            result["cargo"] = "Função Gratificada: " + m_fg.group(1).strip()

    # Símbolo (DAS-3, CAA-4, FDA-1, etc.)
    m_sim = re.search(r"s[íi]mbolo\s+([\w-]+)", text, re.IGNORECASE)
    if m_sim:
        result["simbolo"] = m_sim.group(1)

    # Órgão / Secretaria
    m_org = re.search(
        r"d[aoe]\s+(Secretaria[^,\.\n]+|Ag[eê]ncia[^,\.\n]+|Universidade[^,\.\n]+"
        r"|Companhia[^,\.\n]+|Autarquia[^,\.\n]+|Tribunal[^,\.\n]+|"
        r"Conselho[^,\.\n]+|Funda[cç][aã]o[^,\.\n]+|Departamento[^,\.\n]+)",
        text, re.IGNORECASE
    )
    if m_org:
        result["orgao"] = re.sub(r"\s+", " ", m_org.group(1)).strip()

    # Matrícula
    m_mat = re.search(r"matr[íi]cula\s+(?:n[º°]?\s*)?([\d\./]+)", text, re.IGNORECASE)
    if m_mat:
        result["matricula"] = m_mat.group(1)

    # Data de efeito — formato extenso: "1º de maio de 2026" / "4 de maio de 2026"
    m_data = re.search(
        r"(?:efeito|partir\s+de|retroativo\s+a|retroagindo\s+seus\s+efeitos\s+a)\s+"
        r"(\d+)[oº°]?\s+de\s+(\w+)\s+de\s+(\d{4})",
        text, re.IGNORECASE
    )
    if not m_data:
        # Formato numérico: "a partir de 04.05.2026" ou "04/05/2026"
        m_data = re.search(
            r"(?:efeito|partir\s+de|retroativo\s+a)\s+(\d{2})[/\.](\d{2})[/\.](\d{4})",
            text, re.IGNORECASE
        )
        if m_data:
            d = _parse_date_numerico(m_data.group(1), m_data.group(2), m_data.group(3))
            if d:
                result["data_efeito"] = d
    else:
        d = _parse_date_extenso(m_data.group(1), m_data.group(2), m_data.group(3))
        if d:
            result["data_efeito"] = d

    return result


# ── Decisão Tributária ────────────────────────────────────────────────────────

def parse_decisao_tributaria(text: str) -> Dict:
    result: Dict = {}

    m_int = re.search(r"INTERESSADO:\s+(.+?)\s*(?:CNPJ|CPF|$)", text, re.IGNORECASE)
    if m_int:
        result["empresa"] = m_int.group(1).strip().rstrip(".")

    m_cnpj = re.search(r"CNPJ:\s*([\d\.\/\-]+)", text, re.IGNORECASE)
    if m_cnpj:
        result["cnpj"] = re.sub(r"[^\d]", "", m_cnpj.group(1))

    m_proc = re.search(r"PROCESSO\s+SF\s+N[Oº°]?:\s*([\w\.\-\/]+)", text, re.IGNORECASE)
    if m_proc:
        result["numero_processo"] = m_proc.group(1).strip()

    m_tate = re.search(r"TATE\s+N[Oº°]?:\s*([\w\.\-\/]+)", text, re.IGNORECASE)
    if m_tate:
        result["numero_tate"] = m_tate.group(1).strip()

    m_decisao = re.search(r"DECIS[AÃ]O\s+JT\s+N[Oº°]?([\w\./\(\)]+)", text, re.IGNORECASE)
    if m_decisao:
        result["numero_decisao"] = m_decisao.group(1).strip()

    m_turma = re.search(r"TURMA\s+(\d+|PLENO)", text, re.IGNORECASE)
    if m_turma:
        result["turma"] = m_turma.group(1)

    m_result = re.search(
        r"(PROCED[EÊ]NCIA|IMPROCED[EÊ]NCIA|EXTIN[CÇ][AÃ]O|PARCIALMENTE\s+PROCEDENTE)",
        text, re.IGNORECASE
    )
    if m_result:
        r_map = {
            "PROCEDÊNCIA": "procedente",
            "IMPROCEDÊNCIA": "improcedente",
            "EXTINÇÃO": "extinto",
            "PARCIALMENTE PROCEDENTE": "parcialmente_procedente",
        }
        raw = m_result.group(1).upper()
        for k, v in r_map.items():
            if k in raw or raw in k:
                result["resultado"] = v
                break

    # Julgador (nome após "–" no final das decisões do TATE)
    m_julg = re.search(r"[-–]\s+JATTE?\s*\(\d+\)\s*\.?\s*$", text)
    if m_julg:
        before = text[: m_julg.start()].strip()
        last_line = before.split("\n")[-1].strip()
        if last_line and len(last_line) < 80:
            result["julgador"] = last_line

    return result


# ── Portaria ─────────────────────────────────────────────────────────────────

def parse_portaria(text: str) -> Dict:
    result: Dict = {}

    m = re.search(
        r"PORTARIA\s+([\w/]+)\s+N[Oº°]?\s*([\d\./]+)",
        text, re.IGNORECASE
    )
    if m:
        result["orgao_emissor"] = m.group(1)
        result["numero"] = m.group(2)

    # Ementa: primeira linha de conteúdo
    lines = [l.strip() for l in text.split("\n") if l.strip()]
    for line in lines[1:6]:
        if len(line) > 15 and not re.match(r"^PORTARIA|^A\s+SECRET", line, re.I):
            result["ementa"] = line
            break

    return result


# ── Despacho / extração por tipo ─────────────────────────────────────────────

def parse_by_type(tipo: str, text: str) -> Dict:
    """Dispatcher: chama o parser certo para cada tipo de ato."""
    if tipo == "decreto":
        return parse_decreto(text)
    if tipo == "ato_pessoal":
        return parse_ato_pessoal(text)
    if tipo == "decisao_tributaria":
        return parse_decisao_tributaria(text)
    if tipo == "portaria":
        return parse_portaria(text)
    return {}
