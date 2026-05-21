"""
Pipeline principal de ingestão do DOE-PE.

Uso:
    python src/ingest.py executivo/PoderExecutivo(20260509).pdf
    python src/ingest.py executivo/  # processa todos os PDFs da pasta

O pipeline:
    1. Extrai texto do PDF respeitando colunas
    2. Segmenta em atos individuais
    3. Extrai campos estruturados por tipo
    4. Salva no PostgreSQL (publicacoes + atos + tabelas especializadas)
"""

import re
import sys
from pathlib import Path
from datetime import date
from typing import Optional

import database as db
from config import PDF_DIR
from extractor import extract_pages, full_text
from segmenter import segment
from parser import parse_by_type


# ── Helpers ───────────────────────────────────────────────────────────────────

_MESES_MAP = {
    "janeiro": 1, "fevereiro": 2, "março": 3, "marco": 3, "abril": 4,
    "maio": 5, "junho": 6, "julho": 7, "agosto": 8,
    "setembro": 9, "outubro": 10, "novembro": 11, "dezembro": 12,
}

_SECRETARIA_HEADERS = re.compile(
    r"(?:^|\n)"
    r"(?:SECRET[AÁ]RIA\s+DE\s+(?:ESTADO\s+D[AEO]\s+)?|"
    r"SECRETARIA\s+EXECUTIVA\s+DE\s+)"
    r"([A-ZÁÉÍÓÚÀÂÊÔÃÕÜ][A-ZÁÉÍÓÚÀÂÊÔÃÕÜa-záéíóúàâêôãõü\s\-]+)",
    re.MULTILINE,
)


def _date_from_filename(path: Path) -> date:
    """Extrai data de nomes como PoderExecutivo20260509.pdf ou PoderExecutivo(20260509).pdf"""
    m = re.search(r"(\d{4})(\d{2})(\d{2})", path.name)
    if m:
        return date(int(m.group(1)), int(m.group(2)), int(m.group(3)))
    return date.today()


def _edition_number(text: str) -> Optional[int]:
    m = re.search(r"N[oº°]\s+(\d+)\s+Poder\s+Executivo", text[:600], re.IGNORECASE)
    if m:
        return int(m.group(1))
    m = re.search(r"N[oº°]\s*(\d+)", text[:400], re.IGNORECASE)
    return int(m.group(1)) if m else None


def _current_secretaria(text: str) -> Optional[str]:
    """Retorna a última secretaria mencionada em um bloco de texto."""
    matches = list(_SECRETARIA_HEADERS.finditer(text))
    if matches:
        return re.sub(r"\s+", " ", matches[-1].group(1)).strip().title()
    return None


# ── Salvamento por tipo ───────────────────────────────────────────────────────

def _save_specialized(conn, tipo: str, ato_id: int, parsed: dict) -> None:
    if tipo == "ato_pessoal" and parsed.get("nome"):
        db.insert_ato_pessoal(
            conn,
            ato_id=ato_id,
            numero_ato=parsed.get("numero_ato"),
            tipo_acao=parsed.get("tipo_acao", "outro"),
            nome=parsed["nome"],
            matricula=parsed.get("matricula"),
            cargo=parsed.get("cargo"),
            simbolo=parsed.get("simbolo"),
            orgao=parsed.get("orgao"),
            data_efeito=parsed.get("data_efeito"),
        )

    elif tipo == "decreto" and parsed.get("tipo_credito"):
        db.insert_credito(
            conn,
            ato_id=ato_id,
            orgao_favorecido=parsed.get("orgao_favorecido"),
            valor=parsed.get("valor"),
            tipo_credito=parsed.get("tipo_credito"),
            fonte_recurso=parsed.get("fonte_recurso"),
            codigo_fonte=parsed.get("codigo_fonte"),
            data_retroativa=parsed.get("data_retroativa"),
        )

    elif tipo == "decisao_tributaria":
        db.insert_decisao_tributaria(
            conn,
            ato_id=ato_id,
            numero_tate=parsed.get("numero_tate"),
            numero_processo=parsed.get("numero_processo"),
            cnpj=parsed.get("cnpj"),
            empresa=parsed.get("empresa"),
            turma=parsed.get("turma"),
            resultado=parsed.get("resultado"),
            julgador=parsed.get("julgador"),
            tributo=parsed.get("tributo"),
        )


# ── Pipeline principal ────────────────────────────────────────────────────────

def ingest(pdf_path: Path, reprocess: bool = True) -> None:
    print(f"\n{'='*60}")
    print(f"Processando: {pdf_path.name}")

    data_pub = _date_from_filename(pdf_path)

    # 1. Extração de texto
    pages = extract_pages(pdf_path)
    total_pages = pages[0]["total_pages"] if pages else 0
    doc_text = full_text(pages)
    print(f"  Extraídas {total_pages} páginas ({len(doc_text):,} chars)")

    # 2. Metadados da edição
    numero_edicao = _edition_number(doc_text)

    # 3. Segmentação
    segments = segment(doc_text)
    print(f"  Segmentação: {len(segments)} atos identificados")

    # Contagem por tipo
    tipo_counts: dict = {}
    for s in segments:
        tipo_counts[s["tipo"]] = tipo_counts.get(s["tipo"], 0) + 1
    for t, c in sorted(tipo_counts.items()):
        print(f"    {t}: {c}")

    # 4. Persistência
    with db.get_conn() as conn:
        pub_id = db.upsert_publicacao(
            conn,
            data_publicacao=data_pub,
            numero_edicao=numero_edicao,
            ano=data_pub.year,
            poder="executivo",
            arquivo_path=str(pdf_path.resolve()),
            total_paginas=total_pages,
        )

        if reprocess:
            db.delete_atos_publicacao(conn, pub_id)

        secretaria_atual: Optional[str] = None
        saved = 0

        for seg in segments:
            # Atualiza contexto de secretaria com o texto do próprio segmento
            sec = _current_secretaria(seg["texto"])
            if sec:
                secretaria_atual = sec

            # Extrai campos estruturados
            parsed = parse_by_type(seg["tipo"], seg["texto"])

            # Campos comuns
            numero = parsed.get("numero")
            data_ato = parsed.get("data_ato", data_pub)
            ementa = parsed.get("ementa")
            orgao = parsed.get("orgao_favorecido") or parsed.get("orgao")

            # Serializa campos de data no metadata (não são JSON-serializáveis direto)
            meta_raw = {k: v for k, v in parsed.items()
                        if k not in ("numero", "data_ato", "ementa", "orgao_favorecido", "orgao")}
            metadata = {
                k: (v.isoformat() if hasattr(v, "isoformat") else v)
                for k, v in meta_raw.items()
            }

            try:
                ato_id = db.insert_ato(
                    conn,
                    publicacao_id=pub_id,
                    tipo=seg["tipo"],
                    numero=numero,
                    data_ato=data_ato,
                    secretaria=secretaria_atual,
                    orgao=orgao,
                    ementa=ementa,
                    texto_completo=seg["texto"],
                    pagina_inicio=None,
                    pagina_fim=None,
                    posicao=seg["posicao"],
                    metadata=metadata,
                )
                _save_specialized(conn, seg["tipo"], ato_id, parsed)
                saved += 1
            except Exception as e:
                print(f"  [AVISO] Erro ao salvar ato pos={seg['posicao']}: {e}")
                conn.rollback()
                # Reabre a transação para continuar (PostgreSQL)
                if hasattr(conn, "autocommit"):
                    conn.autocommit = False

    print(f"  Salvo: {saved}/{len(segments)} atos — publicacao_id={pub_id}")


def ingest_dir(directory: Path) -> None:
    pdfs = sorted(directory.glob("*.pdf"))
    if not pdfs:
        print(f"Nenhum PDF encontrado em: {directory}")
        return
    print(f"Encontrados {len(pdfs)} PDFs em {directory}")
    for pdf in pdfs:
        ingest(pdf)


# ── Entrypoint ────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        target = PDF_DIR
    else:
        target = Path(sys.argv[1])

    if target.is_dir():
        ingest_dir(target)
    elif target.is_file():
        ingest(target)
    else:
        print(f"Caminho não encontrado: {target}")
        sys.exit(1)
