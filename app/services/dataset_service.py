from pathlib import Path
from typing import Any
from app.tools.dataset_registry import discover_local_datasets, inspect_dataset_file

def _resolve_dataset_path(dataset_path: str | None) -> str | None:
    if not dataset_path:
        return None
    path = Path(dataset_path).resolve()
    if path.exists():
        return str(path)
    return None

def serialize_dataset(path: str) -> dict[str, Any]:
    resolved = str(Path(path).resolve())
    info = inspect_dataset_file(resolved)
    return {
        "path": resolved,
        "name": Path(resolved).name,
        "group": Path(resolved).parent.name,
        "summary": info.get("summary"),
        "row_count": info.get("row_count"),
        "columns": info.get("columns", []),
    }

def list_datasets() -> list[dict[str, Any]]:
    return [serialize_dataset(path) for path in discover_local_datasets()]
