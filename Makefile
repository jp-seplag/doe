.PHONY: help setup dev-offline ingest-offline search-offline streamlit-offline test-offline fmt-check

PYTHON := .venv/bin/python
PDF ?= executivo/PoderExecutivo20260520.pdf
QUERY ?= educação crédito

help:
	@echo "Targets disponíveis:"
	@echo "  make setup            - instala dependências"
	@echo "  make dev-offline      - prepara ambiente offline (.env/.env)"
	@echo "  make ingest-offline   - ingere PDF no SQLite offline"
	@echo "  make search-offline   - roda busca textual offline"
	@echo "  make streamlit-offline- sobe app Streamlit em modo offline"
	@echo "  make test-offline     - executa testes de sanidade offline"

setup:
	uv venv .venv
	.venv/bin/uv pip install -r requirements.txt

dev-offline:
	mkdir -p .env
	@printf "DATABASE_URL=postgresql://postgres:postgres@127.0.0.1:5433/doe_pe\nOFFLINE_MODE=1\nOFFLINE_DB_PATH=data/doe_offline.db\nPDF_DIR=executivo\n" > .env/.env
	@echo "OK: .env/.env preparado para modo offline"

ingest-offline:
	OFFLINE_MODE=1 OFFLINE_DB_PATH=data/doe_offline.db $(PYTHON) src/ingest.py $(PDF)

search-offline:
	OFFLINE_MODE=1 OFFLINE_DB_PATH=data/doe_offline.db $(PYTHON) src/search.py "$(QUERY)" --limite 5

streamlit-offline:
	OFFLINE_MODE=1 OFFLINE_DB_PATH=data/doe_offline.db $(PYTHON) -m streamlit run app.py

test-offline:
	OFFLINE_MODE=1 OFFLINE_DB_PATH=data/test_offline.db $(PYTHON) -m unittest discover -s tests -p "test_*.py" -v
