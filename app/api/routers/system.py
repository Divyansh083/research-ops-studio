from typing import Any
from fastapi import APIRouter
from fastapi.concurrency import run_in_threadpool
from app.core.config import settings
from app.sandbox.environment import sandbox_ready
from app.services.dataset_service import list_datasets

router = APIRouter()

@router.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}

@router.get("/config")
async def get_config() -> dict[str, Any]:
    def build_runtime_payload() -> dict[str, Any]:
        datasets = list_datasets()
        return {
            "llm_model": settings.llm_model,
            "embedding_model": settings.embedding_model,
            "sandbox_ready": sandbox_ready(),
            "dataset_count": len(datasets),
            "datasets": datasets,
        }
        
    return await run_in_threadpool(build_runtime_payload)
