import base64
import csv
from typing import Any
from pathlib import Path
from fastapi import APIRouter, HTTPException
from fastapi.concurrency import run_in_threadpool
from app.schemas.datasets import DatasetGenerateRequest, DatasetUploadRequest
from app.services.dataset_service import list_datasets, serialize_dataset, _resolve_dataset_path
from app.sandbox.environment import sandbox_ready
from app.tools.dataset_registry import discover_local_datasets, save_uploaded_dataset
from app.graph.agents.dataset_manager import run_dataset_manager_request

router = APIRouter()

@router.get("")
async def get_datasets() -> dict[str, Any]:
    datasets = await run_in_threadpool(list_datasets)
    return {
        "datasets": datasets,
        "sandbox_ready": sandbox_ready(),
    }

@router.get("/preview")
async def preview_dataset(path: str) -> dict[str, Any]:
    valid_datasets = await run_in_threadpool(discover_local_datasets)
    resolved_path = str(Path(path).resolve())
    
    if resolved_path not in valid_datasets:
        raise HTTPException(status_code=403, detail="Dataset not found or unauthorized access.")
    
    def read_dataset() -> dict[str, Any]:
        import pandas as pd
        import json
        suffix = Path(resolved_path).suffix.lower()
        
        try:
            if suffix == ".csv":
                df = pd.read_csv(resolved_path, nrows=100)
            elif suffix in {".xlsx", ".xls"}:
                df = pd.read_excel(resolved_path, nrows=100)
            elif suffix == ".parquet":
                df = pd.read_parquet(resolved_path)[:100]
            elif suffix == ".json":
                # Handle both list of dicts and nested structures
                with open(resolved_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                if isinstance(data, list):
                    df = pd.DataFrame(data[:100])
                elif isinstance(data, dict):
                    # Try to flatten or just show keys
                    df = pd.DataFrame([data])
                else:
                    df = pd.DataFrame([{"content": str(data)}])
            elif suffix in {".pdf", ".docx", ".doc"}:
                # Return a summary for non-tabular files
                return {
                    "columns": ["File Info"],
                    "data": [{"File Info": f"Preview not available for {suffix[1:].upper()} files. Please use RAG tools."}],
                    "total_previewed": 1
                }
            else:
                raise ValueError(f"Unsupported file format: {suffix}")

            # Clean NaNs for JSON serialization
            df = df.where(pd.notnull(df), None)
            
            return {
                "columns": list(df.columns),
                "data": df.to_dict(orient="records"),
                "total_previewed": len(df),
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to read dataset: {str(e)}")

    return await run_in_threadpool(read_dataset)

@router.post("/generate")
async def generate_dataset(payload: DatasetGenerateRequest) -> dict[str, Any]:
    def sync_gen() -> dict[str, Any]:
        return run_dataset_manager_request(
            payload.request,
            available_datasets=discover_local_datasets(),
            selected_dataset_path=_resolve_dataset_path(payload.selected_dataset_path),
        )

    result = await run_in_threadpool(sync_gen)
    dataset_items = result.get("dataset_outputs", [])
    latest_dataset = dataset_items[-1] if dataset_items else None
    
    datasets = await run_in_threadpool(list_datasets)
    
    return {
        "dataset": latest_dataset,
        "selected_dataset_path": result.get("selected_dataset_path"),
        "datasets": datasets,
        "agent_log": result.get("agent_log", []),
        "error_log": result.get("error_log", []),
    }

@router.post("/upload")
async def upload_dataset(payload: DatasetUploadRequest) -> dict[str, Any]:
    # 1. Size Validation (10MB)
    if len(payload.content_base64) > 15_000_000: # Approx 10MB binary
        raise HTTPException(status_code=413, detail="File too large. Max 10MB.")

    # 2. Extension Validation
    from app.tools.dataset_registry import DATASET_EXTENSIONS
    suffix = Path(payload.filename).suffix.lower()
    if suffix not in DATASET_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Unsupported file extension. Allowed: {', '.join(DATASET_EXTENSIONS)}"
        )

    try:
        content = base64.b64decode(payload.content_base64, validate=True)
        if not content:
            raise ValueError("Decoded content is empty.")
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"Invalid or empty base64 payload: {exc}") from exc

    def sync_save() -> str:
        return save_uploaded_dataset(payload.filename, content)

    saved_path = await run_in_threadpool(sync_save)
    serializer = await run_in_threadpool(serialize_dataset, saved_path)
    datasets = await run_in_threadpool(list_datasets)

    return {
        "dataset": serializer,
        "selected_dataset_path": saved_path,
        "datasets": datasets,
    }
