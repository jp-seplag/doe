"""
Camada de persistência com suporte a PostgreSQL (produção) e SQLite (offline).

Modo offline é ativado quando:
- OFFLINE_MODE=1, ou
- DATABASE_URL começa com sqlite://
"""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager, closing
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import urlparse

import psycopg2
import psycopg2.extras

from config import DATABASE_URL


def _is_sqlite_mode() -> bool:
    return os.getenv("OFFLINE_MODE", "0") == "1" or DATABASE_URL.startswith("sqlite://")


IS_SQLITE = _is_sqlite_mode()


def _sqlite_path() -> Path:
    env_path = os.getenv("OFFLINE_DB_PATH", "").strip()
    if env_path:
        return Path(env_path)

    if DATABASE_URL.startswith("sqlite://"):
        raw = DATABASE_URL.replace("sqlite:///", "", 1)
        return Path(raw)

    return Path(__file__).parent.parent / "data" / "doe_offline.db"


def _conn_params() -> dict:
    p = urlparse(DATABASE_URL)
    return {
        "host": p.hostname or "localhost",
        "port": p.port or 5432,
        "dbname": (p.path or "/doe_pe").lstrip("/"),
        "user": p.username or "postgres",
        "password": p.password or "",
        "client_encoding": "utf8",
    }


def _connect_pg() -> psycopg2.extensions.connection:
    try:
        return psycopg2.connect(**_conn_params())
    except UnicodeDecodeError as e:
        msg = e.object.decode("windows-1252", errors="replace")
        raise psycopg2.OperationalError(msg) from None


def _ensure_sqlite_schema(conn: sqlite3.Connection) -> None:
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS publicacoes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            data_publicacao TEXT NOT NULL,
            numero_edicao INTEGER,
            ano INTEGER NOT NULL,
            poder TEXT NOT NULL,
            arquivo_path TEXT,
            total_paginas INTEGER,
            processado_em TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(data_publicacao, poder)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS atos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            publicacao_id INTEGER NOT NULL,
            tipo TEXT NOT NULL,
            numero TEXT,
            data_ato TEXT,
            secretaria TEXT,
            orgao TEXT,
            ementa TEXT,
            texto_completo TEXT NOT NULL,
            pagina_inicio INTEGER,
            pagina_fim INTEGER,
            posicao_no_documento INTEGER,
            metadata TEXT,
            embedding TEXT,
            FOREIGN KEY(publicacao_id) REFERENCES publicacoes(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS atos_pessoais (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ato_id INTEGER NOT NULL,
            numero_ato TEXT,
            tipo_acao TEXT,
            nome TEXT,
            matricula TEXT,
            cargo TEXT,
            simbolo TEXT,
            orgao TEXT,
            data_efeito TEXT,
            observacao TEXT,
            FOREIGN KEY(ato_id) REFERENCES atos(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS creditos_orcamentarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ato_id INTEGER NOT NULL,
            orgao_favorecido TEXT,
            valor REAL,
            tipo_credito TEXT,
            fonte_recurso TEXT,
            codigo_fonte TEXT,
            data_retroativa TEXT,
            FOREIGN KEY(ato_id) REFERENCES atos(id)
        )
        """
    )

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS decisoes_tributarias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ato_id INTEGER NOT NULL,
            numero_tate TEXT,
            numero_processo TEXT,
            cnpj TEXT,
            empresa TEXT,
            turma TEXT,
            resultado TEXT,
            julgador TEXT,
            tributo TEXT,
            FOREIGN KEY(ato_id) REFERENCES atos(id)
        )
        """
    )


@contextmanager
def get_conn():
    if IS_SQLITE:
        db_path = _sqlite_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        _ensure_sqlite_schema(conn)
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()
        return

    conn = _connect_pg()
    conn.autocommit = False
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


@contextmanager
def _cursor(conn):
    cur = conn.cursor()
    try:
        yield cur
    finally:
        cur.close()


def _to_iso(v):
    if v is None:
        return None
    return v.isoformat() if hasattr(v, "isoformat") else str(v)


def upsert_publicacao(
    conn,
    data_publicacao: date,
    numero_edicao: Optional[int],
    ano: int,
    poder: str,
    arquivo_path: str,
    total_paginas: int,
) -> int:
    if IS_SQLITE:
        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO publicacoes
                (data_publicacao, numero_edicao, ano, poder, arquivo_path, total_paginas)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(data_publicacao, poder) DO UPDATE SET
                numero_edicao = excluded.numero_edicao,
                arquivo_path = excluded.arquivo_path,
                total_paginas = excluded.total_paginas,
                processado_em = CURRENT_TIMESTAMP
            """,
            (_to_iso(data_publicacao), numero_edicao, ano, poder, arquivo_path, total_paginas),
        )
        cur.execute(
            "SELECT id FROM publicacoes WHERE data_publicacao = ? AND poder = ?",
            (_to_iso(data_publicacao), poder),
        )
        return cur.fetchone()[0]

    with _cursor(conn) as cur:
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
    with _cursor(conn) as cur:
        sql = "DELETE FROM atos WHERE publicacao_id = ?" if IS_SQLITE else "DELETE FROM atos WHERE publicacao_id = %s"
        cur.execute(sql, (publicacao_id,))


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
    if IS_SQLITE:
        import json

        cur = conn.cursor()
        cur.execute(
            """
            INSERT INTO atos (
                publicacao_id, tipo, numero, data_ato, secretaria, orgao,
                ementa, texto_completo, pagina_inicio, pagina_fim,
                posicao_no_documento, metadata
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                publicacao_id,
                tipo,
                numero,
                _to_iso(data_ato),
                secretaria,
                orgao,
                ementa,
                texto_completo,
                pagina_inicio,
                pagina_fim,
                posicao,
                json.dumps(metadata, ensure_ascii=False),
            ),
        )
        return cur.lastrowid

    with _cursor(conn) as cur:
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
                publicacao_id,
                tipo,
                numero,
                data_ato,
                secretaria,
                orgao,
                ementa,
                texto_completo,
                pagina_inicio,
                pagina_fim,
                posicao,
                psycopg2.extras.Json(metadata),
            ),
        )
        return cur.fetchone()[0]


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
    with _cursor(conn) as cur:
        sql = (
            """
            INSERT INTO atos_pessoais
                (ato_id, numero_ato, tipo_acao, nome, matricula, cargo,
                 simbolo, orgao, data_efeito, observacao)
            VALUES (?,?,?,?,?,?,?,?,?,?)
            """
            if IS_SQLITE
            else
            """
            INSERT INTO atos_pessoais
                (ato_id, numero_ato, tipo_acao, nome, matricula, cargo,
                 simbolo, orgao, data_efeito, observacao)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
        )
        cur.execute(
            sql,
            (ato_id, numero_ato, tipo_acao, nome, matricula, cargo, simbolo, orgao, _to_iso(data_efeito), observacao),
        )


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
    with _cursor(conn) as cur:
        sql = (
            """
            INSERT INTO creditos_orcamentarios
                (ato_id, orgao_favorecido, valor, tipo_credito,
                 fonte_recurso, codigo_fonte, data_retroativa)
            VALUES (?,?,?,?,?,?,?)
            """
            if IS_SQLITE
            else
            """
            INSERT INTO creditos_orcamentarios
                (ato_id, orgao_favorecido, valor, tipo_credito,
                 fonte_recurso, codigo_fonte, data_retroativa)
            VALUES (%s,%s,%s,%s,%s,%s,%s)
            """
        )
        cur.execute(
            sql,
            (ato_id, orgao_favorecido, valor, tipo_credito, fonte_recurso, codigo_fonte, _to_iso(data_retroativa)),
        )


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
    with _cursor(conn) as cur:
        sql = (
            """
            INSERT INTO decisoes_tributarias
                (ato_id, numero_tate, numero_processo, cnpj, empresa,
                 turma, resultado, julgador, tributo)
            VALUES (?,?,?,?,?,?,?,?,?)
            """
            if IS_SQLITE
            else
            """
            INSERT INTO decisoes_tributarias
                (ato_id, numero_tate, numero_processo, cnpj, empresa,
                 turma, resultado, julgador, tributo)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """
        )
        cur.execute(
            sql,
            (ato_id, numero_tate, numero_processo, cnpj, empresa, turma, resultado, julgador, tributo),
        )
