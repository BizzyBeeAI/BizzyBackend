# BizzyBackend

Minimal BizzyBee backend scaffolding for business-performance monitoring.

## Structure

- `backend/` FastAPI app, agent modules, orchestration, security, audit, models and tools.
- `data/demo/` Synthetic demo datasets.
- `tests/` API scaffolding tests.

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn backend.main:app --reload
```

## Test

```bash
pytest tests/test_api.py
```
