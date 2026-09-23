from __future__ import annotations

from fastapi import FastAPI

from backend.api.routes import router as api_router

app = FastAPI(title="BizzyBee Backend", version="0.1.0")
app.include_router(api_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
