"""
Exemplos de consulta ao banco — full-text search e busca estruturada.

Uso interativo:
    python src/search.py "crédito suplementar educação"
    python src/search.py --tipo ato_pessoal --nome "JEFFERSON"
"""

import sys
import argparse
import unicodedata
import psycopg2
import psycopg2.extras
from urllib.parse import urlparse
from config import DATABASE_URL


def _conn_params() -> dict:
    p = urlparse(DATABASE_URL)
    return {
        "host":     p.hostname or "localhost",
        "port":     p.port or 5432,
        "dbname":   (p.path or "/doe_pe").lstrip("/"),
        "user":     p.username or "postgres",
        "password": p.password or "",
        "client_encoding": "utf8",
    }


def _conn():
    return psycopg2.connect(**_conn_params(), cursor_factory=psycopg2.extras.RealDictCursor)


def fulltext_search(query: str, limit: int = 20) -> list:
    """Busca full-text em ementa + texto_completo com ranking."""
    sql = """
        SELECT
            a.id,
            pub.data_publicacao,
            a.tipo,
            a.numero,
            a.secretaria,
            a.ementa,
            ts_rank(a.texto_tsv, q) AS rank,
            ts_headline('portuguese',
                coalesce(a.ementa, '') || ' ' || left(a.texto_completo, 500),
                q, 'MaxWords=20, MinWords=10'
            ) AS trecho
        FROM atos a
        JOIN publicacoes pub ON pub.id = a.publicacao_id,
             to_tsquery('portuguese', %(q)s) q
        WHERE a.texto_tsv @@ q
        ORDER BY rank DESC
        LIMIT %(limit)s
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            # Normaliza acentos no Python (NFD → ASCII) e monta tsquery com prefixo
            def _strip_accents(s: str) -> str:
                return unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode("ascii")

            tsq = " & ".join(
                f"{_strip_accents(w)}:*"
                for w in query.split()
                if w
            )
            cur.execute(sql, {"q": tsq, "limit": limit})
            return cur.fetchall()


def busca_pessoal(nome: str = None, matricula: str = None,
                  tipo_acao: str = None, orgao: str = None,
                  limit: int = 50) -> list:
    """Busca na tabela de atos pessoais."""
    conditions = []
    params = {}

    if nome:
        conditions.append("ap.nome ILIKE %(nome)s")
        params["nome"] = f"%{nome}%"
    if matricula:
        conditions.append("ap.matricula = %(matricula)s")
        params["matricula"] = matricula
    if tipo_acao:
        conditions.append("ap.tipo_acao = %(tipo_acao)s")
        params["tipo_acao"] = tipo_acao
    if orgao:
        conditions.append("ap.orgao ILIKE %(orgao)s")
        params["orgao"] = f"%{orgao}%"

    where = ("WHERE " + " AND ".join(conditions)) if conditions else ""

    sql = f"""
        SELECT
            ap.ato_id,
            ap.tipo_acao,
            ap.nome,
            ap.matricula,
            ap.cargo,
            ap.simbolo,
            ap.orgao,
            ap.data_efeito,
            pub.data_publicacao,
            a.secretaria
        FROM atos_pessoais ap
        JOIN atos a ON a.id = ap.ato_id
        JOIN publicacoes pub ON pub.id = a.publicacao_id
        {where}
        ORDER BY pub.data_publicacao DESC, ap.nome
        LIMIT {limit}
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def busca_decretos(orgao: str = None, tipo_credito: str = None,
                   data_inicio: str = None, data_fim: str = None,
                   limit: int = 50) -> list:
    conditions = ["a.tipo = 'decreto'"]
    params = {}

    if orgao:
        conditions.append("a.orgao ILIKE %(orgao)s")
        params["orgao"] = f"%{orgao}%"
    if tipo_credito:
        conditions.append("co.tipo_credito = %(tipo_credito)s")
        params["tipo_credito"] = tipo_credito
    if data_inicio:
        conditions.append("pub.data_publicacao >= %(data_inicio)s")
        params["data_inicio"] = data_inicio
    if data_fim:
        conditions.append("pub.data_publicacao <= %(data_fim)s")
        params["data_fim"] = data_fim

    join = "LEFT JOIN creditos_orcamentarios co ON co.ato_id = a.id"
    where = "WHERE " + " AND ".join(conditions)

    sql = f"""
        SELECT
            a.id AS ato_id,
            a.numero,
            pub.data_publicacao,
            a.ementa,
            a.orgao,
            co.valor,
            co.tipo_credito,
            co.fonte_recurso
        FROM atos a
        JOIN publicacoes pub ON pub.id = a.publicacao_id
        {join}
        {where}
        ORDER BY pub.data_publicacao DESC
        LIMIT {limit}
    """
    with _conn() as conn:
        with conn.cursor() as cur:
            cur.execute(sql, params)
            return cur.fetchall()


def _print_rows(rows: list, title: str = "") -> None:
    if title:
        print(f"\n{'-'*60}")
        print(f" {title}")
        print(f"{'-'*60}")
    if not rows:
        print("  (sem resultados)")
        return
    for r in rows:
        print()
        for k, v in r.items():
            if v is not None:
                print(f"  {k}: {v}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Busca no DOE-PE")
    parser.add_argument("query", nargs="?", help="Termos de busca full-text")
    parser.add_argument("--nome", help="Busca por nome de servidor")
    parser.add_argument("--matricula", help="Busca por matrícula")
    parser.add_argument("--tipo-acao", help="Tipo de ato pessoal (nomear, exonerar...)")
    parser.add_argument("--orgao", help="Filtro por órgão")
    parser.add_argument("--limite", type=int, default=10)
    args = parser.parse_args()

    if args.query:
        rows = fulltext_search(args.query, limit=args.limite)
        _print_rows(rows, f'Full-text: "{args.query}"')
    elif args.nome or args.matricula or args.tipo_acao:
        rows = busca_pessoal(
            nome=args.nome, matricula=args.matricula,
            tipo_acao=args.tipo_acao, orgao=args.orgao,
            limit=args.limite,
        )
        _print_rows(rows, "Busca pessoal")
    else:
        parser.print_help()
