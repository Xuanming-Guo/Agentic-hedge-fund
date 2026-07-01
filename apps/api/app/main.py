from __future__ import annotations

from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.core.config import get_settings
from app.core.logging import configure_logging
from app.observability.metrics import render_metrics
from app.services.simulation_engine import ENGINE

configure_logging()
settings = get_settings()

app = FastAPI(
    title="Agentic Hedge Fund API",
    description="Simulation-only Qwen agent society backend.",
    version="0.1.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[settings.frontend_origin, "http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict:
    return {
        "status": "ok",
        "service": settings.app_name,
        "simulation_count": len(ENGINE.states),
        "safety": "simulation-only; no real-money trading",
    }


@app.get("/metrics")
def metrics() -> Response:
    return Response(content=render_metrics(), media_type="text/plain; version=0.0.4")


app.include_router(router, prefix="/api")
