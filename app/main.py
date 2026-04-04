from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import datasets, research, sandbox, system
from app.core.config import settings


def get_allowed_origins() -> list[str]:
    return [
        origin.strip()
        for origin in settings.cors_allowed_origins.split(",")
        if origin.strip()
    ]

def create_app() -> FastAPI:
    app = FastAPI(title="Multi-Agent Research Assistant API", version="0.3.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=get_allowed_origins(),
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(system.router, prefix="/api", tags=["system"])
    app.include_router(datasets.router, prefix="/api/datasets", tags=["datasets"])
    app.include_router(research.router, prefix="/api/research", tags=["research"])
    app.include_router(sandbox.router, prefix="/api/sandbox", tags=["sandbox"])

    @app.get("/health", tags=["system"], summary="Legacy health check")
    async def root_health():
        return {"status": "ok"}

    return app

app = create_app()
