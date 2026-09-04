"""CaseFile FastAPI application.

The backend is the authoritative financial engine; the browser is never the
source of truth. Run with:  uvicorn backend.main:app --port 8000
"""
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from . import config
from .api import (
    routes_approve,
    routes_audit,
    routes_cases,
    routes_investigate,
    routes_metrics,
)

app = FastAPI(title="CaseFile", version="1.0.0")

# CORS: allow all for local development.
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/health")
def health():
    return {"status": "ok"}


@app.get("/api/readiness")
def readiness():
    """Report whether the dataset is loaded and how large it is.

    The frontend uses this to decide whether the backend is truly ready to
    serve authoritative financial data (vs. merely up)."""
    from .api import store
    from .llm import providers

    try:
        tables = store.get_tables()
        meta = store._load_meta()
        payments = len(tables.get("payments", []))
        ready = payments > 0
        return {
            "ready": ready,
            "canonical_transactions": meta.get("canonical_transactions", len(tables.get("orders", []))),
            "total_records": meta.get("total_records", sum(len(v) for v in tables.values())),
            "dataset_seed": meta.get("seed"),
            "ai_provider": providers.selected_name(),
            "ai_configured": providers.is_ai_configured(),
            "ai_reachable": providers.is_ai_reachable(),
            "require_ai": config.REQUIRE_AI,
            "fallback_enabled": providers.fallback_allowed(),
        }
    except Exception as exc:  # noqa: BLE001
        return {"ready": False, "error": str(exc)}


app.include_router(routes_cases.router)
app.include_router(routes_investigate.router)
app.include_router(routes_approve.router)
app.include_router(routes_metrics.router)
app.include_router(routes_audit.router)
