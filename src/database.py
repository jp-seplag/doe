"""
Operações de banco de dados usando psycopg2 puro.
Usa transações explícitas para garantir consistência por edição.
"""

import psycopg2
import psycopg2.extras
from contextlib import contextmanager
from datetime import date
from typing import Optional
from urllib.parse import urlparse

from config import DATABASE_URL


def _conn_params() -> dict:
    """
    Parseia DATABASE_URL e retorna kwargs para psycopg2.connect().
    Evita que o psycopg2 processe a string DSN diretamente, o que
    causa UnicodeDecodeError em Windows com locale português.
    """
    p = urlparse(DATABASE_URL)
    return {
        "host":     p.hostname or "localhost",
        "port":     p.port or 5432,
        "dbname":   (p.path or "/doe_pe").lstrip("/"),
        "user":     p.username or "postgres",
        "password": p.password or "",
        "client_encoding": "utf8",
    }


def _connect_safe() -> psycopg2.extensions.connection:
    """
    psycopg2 raises UnicodeDecodeError on Windows PT-BR systems when the
    connection fails, because libpq returns error messages in Windows-1252
    but Python 3 tries to decode them as UTF-8.
    """
    try:
        return psycopg2.connect(**_conn_params())
    except UnicodeDecodeError as e:
        msg = e.object.decode("windows-1252", errors="replace")
        raise psycopg2.OperationalError(msg) from None


@contextmanager
def get_conn():
    conn = _connect_safe()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


# ── Publicação ────────────────────────────────────────────────────────────────

def upsert_publicacao(
    conn,
    data_publicacao: date,
    numero_edicao: Optional[int],
    ano: int,
    poder: str,
    arquivo_path: str,
    total_paginas: int,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO publicacoes
                (data_publicacao, numero_edicao, ano, poder, arquivo_path, total_paginas)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (data_publicacao, poder) DO UPDATE
                SET numero_edicao = EXCLUDED.numero_edicao,
                    arquivo_path  = EXCLUDED.arquivo_path,
                    total_paginas = EXCLUDED.total_paginas,
                    processado_em = now()
            RETURNING id
            """,
            (data_publicacao, numero_edicao, ano, poder, arquivo_path, total_paginas),
        )
        return cur.fetchone()[0]


def delete_atos_publicacao(conn, publicacao_id: int) -> None:
    """Remove atos anteriores para reprocessamento limpo da mesma edição."""
    with conn.cursor() as cur:
        cur.execute("DELETE FROM atos WHERE publicacao_id = %s", (publicacao_id,))


# ── Ato ───────────────────────────────────────────────────────────────────────

def insert_ato(
    conn,
    publicacao_id: int,
    tipo: str,
    numero: Optional[str],
    data_ato: Optional[date],
    secretaria: Optional[str],
    orgao: Optional[str],
    ementa: Optional[str],
    texto_completo: str,
    pagina_inicio: Optional[int],
    pagina_fim: Optional[int],
    posicao: int,
    metadata: dict,
) -> int:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO atos (
                publicacao_id, tipo, numero, data_ato, secretaria, orgao,
                ementa, texto_completo, pagina_inicio, pagina_fim,
                posicao_no_documento, metadata
            ) VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            RETURNING id
            """,
            (
                publicacao_id, tipo, numero, data_ato, secretaria, orgao,
                ementa, texto_completo, pagina_inicio, pagina_fim,
                posicao, psycopg2.extras.Json(metadata),
            ),
        )
        return cur.fetchone()[0]


# ── Ato Pessoal ───────────────────────────────────────────────────────────────

def insert_ato_pessoal(
    conn,
    ato_id: int,
    numero_ato: Optional[str],
    tipo_acao: str,
    nome: str,
    matricula: Optional[str],
    cargo: Optional[str],
    simbolo: Optional[str],
    orgao: Optional[str],
    data_efeito: Optional[date],
    observacao: Optional[str] = None,
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO atos_pessoais
                (ato_id, numero_ato, tipo_acao, nome, matricula, cargo,
                 simbolo, orgao, data_efeito, observacao)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (ato_id, numero_ato, tipo_acao, nome, matricula, cargo,
             simbolo, orgao, data_efeito, observacao),
        )


# ── Crédito Orçamentário ──────────────────────────────────────────────────────

def insert_credito(
    conn,
    ato_id: int,
    orgao_favorecido: Optional[str],
    valor: Optional[float],
    tipo_credito: Optional[str],
    fonte_recurso: Optional[str],
    codigo_fonte: Optional[str],
    data_retroativa: Optional[date],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO creditos_orcamentarios
                (ato_id, orgao_favorecido, valor, tipo_credito,
                 fonte_recurso, codigo_fonte, data_retroativa)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """,
            (ato_id, orgao_favorecido, valor, tipo_credito,
             fonte_recurso, codigo_fonte, data_retroativa),
        )


# ── Decisão Tributária ────────────────────────────────────────────────────────

def insert_decisao_tributaria(
    conn,
    ato_id: int,
    numero_tate: Optional[str],
    numero_processo: Optional[str],
    cnpj: Optional[str],
    empresa: Optional[str],
    turma: Optional[str],
    resultado: Optional[str],
    julgador: Optional[str],
    tributo: Optional[str],
) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO decisoes_tributarias
                (ato_id, numero_tate, numero_processo, cnpj, empresa,
                 turma, resultado, julgador, tributo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """,
            (ato_id, numero_tate, numero_processo, cnpj, empresa,
             turma, resultado, julgador, tributo),
        )
