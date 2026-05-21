import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent / "src"))

import streamlit as st
import pandas as pd
import psycopg2.extras
from database import get_conn
from search import fulltext_search, busca_pessoal, busca_decretos

st.set_page_config(page_title="DOE-PE", page_icon="📰", layout="wide")

st.title("📰 Diário Oficial de Pernambuco")
st.caption("Poder Executivo — consulta ao acervo ingerido")


# ── Detalhes completos de um ato ──────────────────────────────────────────────

def _busca_ato(ato_id: int) -> dict | None:
    with get_conn() as conn:
        with conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor) as cur:
            cur.execute("""
                SELECT a.*, pub.data_publicacao, pub.numero_edicao, pub.total_paginas
                FROM atos a
                JOIN publicacoes pub ON pub.id = a.publicacao_id
                WHERE a.id = %s
            """, (ato_id,))
            row = cur.fetchone()
            if not row:
                return None
            ato = dict(row)

            if ato["tipo"] == "ato_pessoal":
                cur.execute("SELECT * FROM atos_pessoais WHERE ato_id = %s", (ato_id,))
                ato["_pessoal"] = [dict(r) for r in cur.fetchall()]
            elif ato["tipo"] == "decreto":
                cur.execute("SELECT * FROM creditos_orcamentarios WHERE ato_id = %s", (ato_id,))
                ato["_creditos"] = [dict(r) for r in cur.fetchall()]
            elif ato["tipo"] == "decisao_tributaria":
                cur.execute("SELECT * FROM decisoes_tributarias WHERE ato_id = %s", (ato_id,))
                ato["_decisoes"] = [dict(r) for r in cur.fetchall()]
    return ato


# ── Modal de detalhe ─────────────────────────────────────────────────────────

@st.dialog("Detalhes do ato", width="large")
def _modal_detalhe(ato_id: int):
    ato = _busca_ato(ato_id)
    if not ato:
        st.error("Ato não encontrado.")
        return

    tipo = ato["tipo"].replace("_", " ").title()
    numero = f" nº {ato['numero']}" if ato.get("numero") else ""
    st.subheader(f"{tipo}{numero}")

    col1, col2, col3 = st.columns(3)
    col1.metric("Publicado em", str(ato["data_publicacao"]))
    col2.metric("Edição", f"nº {ato['numero_edicao']}" if ato.get("numero_edicao") else "—")
    col3.metric("Páginas da edição", ato.get("total_paginas", "—"))

    if ato.get("secretaria"):
        st.caption(f"**Secretaria:** {ato['secretaria']}")
    if ato.get("orgao"):
        st.caption(f"**Órgão:** {ato['orgao']}")
    if ato.get("data_ato"):
        st.caption(f"**Data do ato:** {ato['data_ato']}")
    if ato.get("ementa"):
        st.info(ato["ementa"])

    if ato.get("_pessoal"):
        st.markdown("**Servidores envolvidos**")
        df = pd.DataFrame(ato["_pessoal"]).drop(columns=["id", "ato_id"], errors="ignore")
        df = df.rename(columns={
            "tipo_acao": "Ação", "nome": "Nome", "matricula": "Matrícula",
            "cargo": "Cargo", "simbolo": "Símbolo", "orgao": "Órgão",
            "data_efeito": "Data efeito", "numero_ato": "Nº ato", "observacao": "Obs.",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

    if ato.get("_creditos"):
        st.markdown("**Créditos orçamentários**")
        df = pd.DataFrame(ato["_creditos"]).drop(columns=["id", "ato_id"], errors="ignore")
        if "valor" in df.columns:
            df["valor"] = df["valor"].apply(
                lambda x: f"R$ {x:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                if x else ""
            )
        df = df.rename(columns={
            "orgao_favorecido": "Órgão favorecido", "valor": "Valor",
            "tipo_credito": "Tipo", "fonte_recurso": "Fonte",
            "codigo_fonte": "Cód. fonte", "data_retroativa": "Data retroativa",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

    if ato.get("_decisoes"):
        st.markdown("**Decisões tributárias**")
        df = pd.DataFrame(ato["_decisoes"]).drop(columns=["id", "ato_id"], errors="ignore")
        df = df.rename(columns={
            "numero_tate": "Nº TATE", "numero_processo": "Processo",
            "cnpj": "CNPJ", "empresa": "Empresa", "turma": "Turma",
            "resultado": "Resultado", "julgador": "Julgador", "tributo": "Tributo",
        })
        st.dataframe(df, use_container_width=True, hide_index=True)

    st.divider()
    st.markdown("**Texto completo**")
    st.text_area(
        label="texto_completo",
        value=ato.get("texto_completo", ""),
        height=400,
        disabled=True,
        label_visibility="collapsed",
    )


# ── Métricas rápidas ─────────────────────────────────────────────────────────

@st.cache_data(ttl=60)
def _stats():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM publicacoes")
            edicoes = cur.fetchone()[0]
            cur.execute("SELECT COUNT(*) FROM atos")
            atos = cur.fetchone()[0]
            cur.execute("SELECT MIN(data_publicacao), MAX(data_publicacao) FROM publicacoes")
            inicio, fim = cur.fetchone()
    return edicoes, atos, inicio, fim

try:
    edicoes, total_atos, inicio, fim = _stats()
    db_error = None
except Exception as e:  # noqa: BLE001
    edicoes, total_atos, inicio, fim = 0, 0, None, None
    db_error = str(e)

col1, col2, col3, col4 = st.columns(4)
col1.metric("Edições", edicoes)
col2.metric("Total de atos", f"{total_atos:,}")
col3.metric("Início", str(inicio) if inicio else "—")
col4.metric("Última edição", str(fim) if fim else "—")

if db_error:
    st.warning(
        "Banco de dados indisponível no momento. "
        "Suba/configure o PostgreSQL para habilitar buscas e métricas reais."
    )
    st.caption(f"Detalhe técnico: {db_error}")

st.divider()

# Resultados persistem no session_state para sobreviver ao rerun do botão "Ver"
for _k in ("rows_texto", "rows_pessoal", "rows_decretos"):
    if _k not in st.session_state:
        st.session_state[_k] = []


# ── Abas ─────────────────────────────────────────────────────────────────────

aba_texto, aba_pessoal, aba_decretos = st.tabs([
    "🔍 Busca por texto",
    "👤 Atos de pessoal",
    "📋 Decretos",
])


# ── Aba 1: Busca full-text ────────────────────────────────────────────────────

with aba_texto:
    st.subheader("Busca full-text")
    st.caption("Pesquisa em ementa e texto completo de todos os atos.")

    col_q, col_lim, col_btn = st.columns([4, 1, 1])
    with col_q:
        query = st.text_input("Termos de busca", placeholder="ex: crédito suplementar educação")
    with col_lim:
        limite = st.number_input("Resultados", min_value=5, max_value=100, value=20, step=5)
    with col_btn:
        st.write("")
        buscar_t = st.button("Buscar", key="btn_texto", type="primary", use_container_width=True)

    if buscar_t and query:
        with st.spinner("Buscando..."):
            try:
                st.session_state.rows_texto = fulltext_search(query, limit=int(limite))
            except Exception as e:
                st.error(f"Erro na busca: {e}")
                st.session_state.rows_texto = []

    rows = st.session_state.rows_texto
    if buscar_t and not rows:
        st.info("Nenhum resultado encontrado.")
    elif rows:
        st.success(f"{len(rows)} resultado(s) encontrado(s)")
        for r in rows:
            data = r["data_publicacao"]
            tipo = r["tipo"].replace("_", " ").title()
            numero = f" nº {r['numero']}" if r.get("numero") else ""
            secretaria = f" — {r['secretaria']}" if r.get("secretaria") else ""

            with st.container(border=True):
                col_info, col_ver = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**{tipo}{numero}** · {data}{secretaria}")
                    if r.get("ementa"):
                        st.caption(r["ementa"])
                    if r.get("trecho"):
                        trecho = r["trecho"].replace("<b>", "**").replace("</b>", "**")
                        st.markdown(f"_{trecho}_")
                with col_ver:
                    if st.button("Ver", key=f"ver_ft_{r['id']}", use_container_width=True):
                        _modal_detalhe(r["id"])


# ── Aba 2: Atos de pessoal ────────────────────────────────────────────────────

with aba_pessoal:
    st.subheader("Atos de pessoal")
    st.caption("Nomeações, exonerações, cessões e outros atos de pessoal.")

    col1, col2 = st.columns(2)
    with col1:
        nome = st.text_input("Nome do servidor", placeholder="ex: João Silva")
        tipo_acao = st.selectbox(
            "Tipo de ação",
            ["(todos)", "nomear", "exonerar", "ceder", "designar",
             "dispensar", "promover", "remover", "aposentar"],
        )
    with col2:
        matricula = st.text_input("Matrícula SGP", placeholder="ex: 123456/01")
        orgao = st.text_input("Órgão / Secretaria", placeholder="ex: Educação")

    col_sl, col_bp = st.columns([4, 1])
    with col_sl:
        limite_p = st.slider("Máximo de resultados", 10, 200, 50, step=10)
    with col_bp:
        st.write("")
        buscar_p = st.button("Buscar", key="btn_pessoal", type="primary", use_container_width=True)

    if buscar_p:
        filtros = {
            "nome": nome or None,
            "matricula": matricula or None,
            "tipo_acao": None if tipo_acao == "(todos)" else tipo_acao,
            "orgao": orgao or None,
        }
        if not any(filtros.values()):
            st.warning("Preencha ao menos um filtro.")
        else:
            with st.spinner("Buscando..."):
                try:
                    st.session_state.rows_pessoal = busca_pessoal(**filtros, limit=limite_p)
                except Exception as e:
                    st.error(f"Erro: {e}")
                    st.session_state.rows_pessoal = []

    rows = st.session_state.rows_pessoal
    if buscar_p and not rows:
        st.info("Nenhum resultado.")
    elif rows:
        st.success(f"{len(rows)} registro(s) encontrado(s)")
        for r in rows:
            nome_r = r.get("nome", "—")
            acao = r.get("tipo_acao", "").title()
            cargo = r.get("cargo", "")
            orgao_r = r.get("orgao", "")
            data = r.get("data_publicacao", "")
            ato_id = r.get("ato_id")

            with st.container(border=True):
                col_info, col_ver = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**{nome_r}** · {acao}")
                    partes = [p for p in [cargo, orgao_r] if p]
                    if partes:
                        st.caption(" — ".join(partes))
                    st.caption(f"Publicado em {data}")
                with col_ver:
                    if ato_id and st.button("Ver", key=f"ver_p_{ato_id}_{nome_r}", use_container_width=True):
                        _modal_detalhe(ato_id)


# ── Aba 3: Decretos ──────────────────────────────────────────────────────────

with aba_decretos:
    st.subheader("Decretos")

    col1, col2 = st.columns(2)
    with col1:
        orgao_d = st.text_input("Órgão favorecido", placeholder="ex: Saúde", key="orgao_d")
        tipo_credito = st.selectbox(
            "Tipo de crédito",
            ["(todos)", "suplementar", "especial", "extraordinário"],
        )
    with col2:
        data_ini = st.date_input("Data inicial", value=None, key="d_ini")
        data_fim_d = st.date_input("Data final", value=None, key="d_fim")

    col_sl, col_bd = st.columns([4, 1])
    with col_sl:
        limite_d = st.slider("Máximo de resultados", 10, 200, 50, step=10, key="lim_d")
    with col_bd:
        st.write("")
        buscar_d = st.button("Buscar", key="btn_decretos", type="primary", use_container_width=True)

    if buscar_d:
        with st.spinner("Buscando..."):
            try:
                st.session_state.rows_decretos = busca_decretos(
                    orgao=orgao_d or None,
                    tipo_credito=None if tipo_credito == "(todos)" else tipo_credito,
                    data_inicio=str(data_ini) if data_ini else None,
                    data_fim=str(data_fim_d) if data_fim_d else None,
                    limit=limite_d,
                )
            except Exception as e:
                st.error(f"Erro: {e}")
                st.session_state.rows_decretos = []

    rows = st.session_state.rows_decretos
    if buscar_d and not rows:
        st.info("Nenhum resultado.")
    elif rows:
        st.success(f"{len(rows)} decreto(s) encontrado(s)")
        for r in rows:
            numero_r = r.get("numero", "s/n")
            data = r.get("data_publicacao", "")
            ementa = r.get("ementa", "")
            orgao_r = r.get("orgao", "")
            valor = r.get("valor")
            ato_id = r.get("ato_id")

            with st.container(border=True):
                col_info, col_ver = st.columns([5, 1])
                with col_info:
                    st.markdown(f"**Decreto nº {numero_r}** · {data}")
                    if ementa:
                        st.caption(ementa)
                    partes = []
                    if orgao_r:
                        partes.append(orgao_r)
                    if valor:
                        valor_fmt = f"R$ {valor:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
                        partes.append(valor_fmt)
                    if partes:
                        st.caption(" · ".join(partes))
                with col_ver:
                    if ato_id and st.button("Ver", key=f"ver_d_{ato_id}", use_container_width=True):
                        _modal_detalhe(ato_id)
