from __future__ import annotations

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from backend.api.routes import router as api_router

# Load environment variables from .env file
load_dotenv()

app = FastAPI(title="BizzyBee Backend", version="0.1.0")
app.include_router(api_router)

# Enable CORS for local development
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000", "*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router)

@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
