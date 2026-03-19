# KFabric

KFabric is a Python-first MVP for documentary corpus discovery, qualification,
fragment salvage, consolidation, and pre-index preparation for future RAG
usage.

## Highlights

- FastAPI REST API
- Native MCP server in Python
- Celery worker scaffold
- Lightweight server-rendered web UI with Jinja2, HTMX and Alpine.js
- PostgreSQL-ready SQLAlchemy models with Alembic migrations
- Corpus-first workflow before full RAG chat

## Quickstart

```bash
python3.12 -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
cp .env.example .env
uvicorn kfabric.api.app:app --reload
```

## Main flows

1. Create a search query
2. Discover candidate documents
3. Collect and parse candidate documents
4. Score and decide on each document
5. Salvage useful fragments from rejected documents
6. Consolidate fragments and build a synthesis
7. Assemble the final corpus
8. Prepare index artifacts for future RAG usage

