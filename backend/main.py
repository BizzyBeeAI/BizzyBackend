from __future__ import annotations

import os

from dotenv import load_dotenv
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.api.routes import router as api_router

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="BizzyBee Backend", version="0.1.0")

# Enable direct browser requests from configured frontends.
cors_origins = [
    origin.strip()
    for origin in os.getenv(
        "CORS_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173,http://localhost:3000,http://127.0.0.1:3000",
    ).split(",")
    if origin.strip()
]
app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
