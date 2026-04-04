import mimetypes
from pathlib import Path
from fastapi import APIRouter, HTTPException, Path as FastAPIPath
from fastapi.responses import FileResponse
from app.sandbox.environment import get_sandbox_workspace

router = APIRouter()

@router.get("/files/{path:path}")
async def serve_sandbox_file(
    path: str = FastAPIPath(..., pattern=r"^[\w./-]*[\w.-]+$")
) -> FileResponse:
    workspace = get_sandbox_workspace()
    file_path = (workspace / path).resolve()
    
    # Path Traversal Prevention
    if not file_path.resolve().is_relative_to(workspace.resolve()):
        raise HTTPException(status_code=403, detail="Path traversal detected")

    if not file_path.exists() or not file_path.is_file():
        raise HTTPException(status_code=404, detail="File not found")
        
    content_type, _ = mimetypes.guess_type(file_path.name)
    return FileResponse(
        path=str(file_path),
        media_type=content_type or "application/octet-stream",
        filename=file_path.name,
    )
