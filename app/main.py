from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routers import datasets, research, sandbox, system

def create_app() -> FastAPI:
    app = FastAPI(title="Multi-Agent Research Assistant API", version="0.3.0")
    
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://localhost:3000",
            "http://127.0.0.1:3000",
            "http://localhost:3001",
            "http://127.0.0.1:3001",
        ],
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
