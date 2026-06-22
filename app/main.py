from fastapi import FastAPI

from app.auth import router as auth_router
from app.health import router as health_router
from app.root import router as root_router

app = FastAPI(
    title="baby-backend",
    description="A minimal FastAPI backend service",
    version="0.1.0",
)

app.include_router(root_router)
app.include_router(health_router)
app.include_router(auth_router)
