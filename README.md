# DOE-PE — Diário Oficial de Pernambuco

Pipeline de ingestão e busca para o Diário Oficial do Estado de Pernambuco (Poder Executivo). Baixa edições diárias em PDF, extrai e estrutura atos oficiais e armazena em PostgreSQL com suporte a busca textual e consultas estruturadas.

---

## Funcionalidades

- **Download automático** das edições diárias direto do repositório oficial do CEPE
- **Extração de PDF** com suporte a layouts multi-coluna (2–3 colunas por página)
- **Segmentação e classificação** de 8 tipos de atos: decretos, portarias, resoluções, instruções normativas, atos pessoais, decisões tributárias, entre outros
- **Parsing estruturado** por tipo de ato: número, datas, órgão, ementa, créditos orçamentários, dados de pessoal, etc.
- **Busca full-text** em português com ranqueamento TF-IDF, remoção de acentos e stemming
- **Consultas estruturadas** por nome de servidor, tipo de ação, secretaria, intervalo de datas
- **Interface web** (Streamlit) para consultas sem linha de comando
- **Agendamento automático** via Agendador de Tarefas do Windows (download diário às 07h30)
- **Pronto para embeddings**: extensão pgvector carregada, campo `embedding` na tabela de atos

---

## Tecnologias

| Camada | Tecnologia |
|--------|-----------|
| Linguagem | Python 3.13+ |
| Banco de dados | PostgreSQL 16 + pgvector |
| Extração de PDF | pdfplumber |
| Driver PostgreSQL | psycopg2-binary |
| Configuração | python-dotenv |
| Interface web | Streamlit |
| Infraestrutura | Docker Compose |
| Automação (Windows) | PowerShell + Agendador de Tarefas |

---

## Estrutura do Projeto

```
DOE/
├── src/
│   ├── config.py          # Leitura de variáveis de ambiente
│   ├── downloader.py      # Download dos PDFs (diário, por data, por intervalo)
│   ├── extractor.py       # Extração de texto com suporte a múltiplas colunas
│   ├── segmenter.py       # Segmentação do texto em atos individuais
│   ├── parser.py          # Extração de campos estruturados por tipo de ato
│   ├── database.py        # Operações PostgreSQL (psycopg2)
│   ├── ingest.py          # Pipeline principal: PDF → banco de dados
│   └── search.py          # Busca full-text e consultas estruturadas
│
├── sql/
│   └── schema.sql         # Schema PostgreSQL (tabelas, índices, triggers, view)
│
├── executivo/             # PDFs baixados (não versionar)
├── logs/                  # Logs do downloader (não versionar)
│
├── app.py                 # Interface web Streamlit
├── docker-compose.yml     # PostgreSQL + pgvector
├── setup_task.ps1         # Configura tarefa agendada no Windows
├── requirements.txt       # Dependências Python
└── .env/
    └── .env.example       # Template de variáveis de ambiente
```

---

## Configuração

### 1. Pré-requisitos

- Python 3.13+
- Docker e Docker Compose
- Windows (para o agendamento automático via `setup_task.ps1`)

### 2. Clonar, criar venv e instalar dependências

```powershell
git clone <url-do-repositorio>
cd DOE
python -m venv .venv
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
pip install streamlit
```

### 3. Configurar variáveis de ambiente

Copie o template e ajuste conforme necessário:

```powershell
copy .env\.env.example .env\.env
```

Conteúdo do `.env`:

```env
DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/doe_pe
PDF_DIR=executivo
```

> **Atenção:** use `127.0.0.1` (não `localhost`) e porta `5433` para garantir que a conexão vai para o container Docker, evitando conflito com instalações locais do PostgreSQL.

### 4. Subir o banco de dados

```powershell
docker-compose up -d
```

O schema é carregado automaticamente na primeira inicialização a partir de `sql/schema.sql`.

> Se o volume já existia sem o schema aplicado, execute manualmente:
> ```powershell
> docker exec -i doe_pe_postgres psql -U postgres -d doe_pe < sql/schema.sql
> ```

### 5. (Opcional) Configurar download automático diário

Execute como administrador para registrar a tarefa no Agendador do Windows (executa às 07h30):

```powershell
powershell -ExecutionPolicy Bypass -File setup_task.ps1
```

---

## Uso

### Download de edições

```powershell
# Edição de hoje
python src/downloader.py

# Data específica
python src/downloader.py --date 2025-03-15

# Últimos N dias
python src/downloader.py --days 30

# Intervalo de datas
python src/downloader.py --start 2025-01-01 --end 2025-03-31
```

Os arquivos são salvos em `executivo/PoderExecutivo{YYYYMMDD}.pdf`.

### Ingestão (PDF → banco de dados)

```powershell
# Arquivo único
python src/ingest.py executivo/PoderExecutivo20260509.pdf

# Todos os PDFs de uma pasta
python src/ingest.py executivo/
```

### Interface web (Streamlit)

```powershell
$env:PYTHONPATH = "src"
.venv\Scripts\python.exe -m streamlit run app.py
```

Acesse **http://localhost:8501** no navegador. A interface oferece três abas:

- **Busca por texto** — full-text com destaque do trecho relevante e controle de limite
- **Atos de pessoal** — filtros por nome, matrícula, tipo de ação e órgão
- **Decretos** — filtros por órgão, tipo de crédito e intervalo de datas

### Busca via linha de comando

```powershell
$env:PYTHONPATH = "src"

# Busca full-text
python src/search.py "crédito suplementar educação"

# Por nome de servidor
python src/search.py --nome "JEFFERSON"

# Por tipo de ação e órgão
python src/search.py --tipo-acao "nomear" --orgao "Educação"
```

---

## Schema do Banco de Dados

| Tabela | Descrição |
|--------|-----------|
| `publicacoes` | Edições do DOE (uma por data de publicação) |
| `atos` | Atos individuais com texto completo e vetor TSV para busca |
| `atos_pessoais` | Dados estruturados de atos de pessoal (nomeações, exonerações, etc.) |
| `creditos_orcamentarios` | Créditos orçamentários de decretos |
| `decisoes_tributarias` | Decisões do Tribunal Administrativo Tributário (TATE) |
| `vw_pessoal_completo` | View: dados de pessoal com contexto da publicação |

Índices: full-text (`tsvector`), trigrama (`pg_trgm`), tipo, secretaria, data, número.

---

## Tipos de Atos Reconhecidos

| Tipo interno | Descrição |
|-------------|-----------|
| `decreto` | Decretos do Executivo |
| `portaria` | Portarias |
| `resolucao` | Resoluções |
| `instrucao_normativa` | Instruções Normativas |
| `ato_pessoal` | Atos de pessoal (nomeação, exoneração, promoção, etc.) |
| `decisao_tributaria` | Decisões do TATE |
| `materia` | Matérias editoriais |

---

## Dependências

```
pdfplumber>=0.11.4
psycopg2-binary>=2.9.9
python-dotenv>=1.0.1
streamlit
```

---

## Observações

- Domingos são ignorados automaticamente pelo downloader (sem publicação).
- O pipeline de ingestão continua em caso de falha em atos individuais (rollback por ato, não por edição).
- Reprocessamento de um PDF apaga os atos anteriores antes de reingerir.
- O campo `embedding` (pgvector) está presente no schema, mas a geração de embeddings não está implementada — preparado para busca semântica futura.
- Logs do agendamento em `logs/downloader.log`.
