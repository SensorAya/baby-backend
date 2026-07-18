import os

from fastapi import FastAPI

from app.auth import router as auth_router
from app.health import router as health_router
from app.monitoring import router as monitoring_router
from app.reports import router as reports_router
from app.root import router as root_router

disable_docs = os.environ.get("DISABLE_DOCS", "").lower() in ("1", "true", "yes")

app = FastAPI(
    title="baby-backend",
    description="A minimal FastAPI backend service",
    version="0.1.0",
    docs_url=None if disable_docs else "/docs",
    redoc_url=None if disable_docs else "/redoc",
    openapi_url=None if disable_docs else "/openapi.json",
)

app.include_router(root_router)
app.include_router(health_router)
app.include_router(auth_router)
app.include_router(monitoring_router)
app.include_router(reports_router)
