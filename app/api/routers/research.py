import json
from typing import Any, AsyncGenerator
from fastapi import APIRouter
from fastapi.responses import StreamingResponse
from fastapi.concurrency import run_in_threadpool

from app.schemas.research import ResearchRunRequest
from app.services.research_service import make_initial_state, merge_update, serialize_state
from app.services.dataset_service import _resolve_dataset_path
from app.tools.dataset_registry import discover_local_datasets
from app.graph.graph import research_graph

router = APIRouter()

@router.post("/run")
async def run_research(payload: ResearchRunRequest) -> dict[str, Any]:
    available_datasets = await run_in_threadpool(discover_local_datasets)
    state = make_initial_state(
        payload.query,
        available_datasets=available_datasets,
        selected_dataset_path=_resolve_dataset_path(payload.selected_dataset_path),
    )
    
    def sync_invoke() -> dict[str, Any]:
        return research_graph.invoke(state)

    result = await run_in_threadpool(sync_invoke)
    snapshot = serialize_state(result)
    snapshot["available_datasets"] = available_datasets
    return snapshot

@router.post("/stream")
async def stream_research(payload: ResearchRunRequest) -> StreamingResponse:
    available_datasets = await run_in_threadpool(discover_local_datasets)
    initial_state = make_initial_state(
        payload.query,
        available_datasets=available_datasets,
        selected_dataset_path=_resolve_dataset_path(payload.selected_dataset_path),
    )

    async def async_event_stream() -> AsyncGenerator[str, None]:
        current_state: dict[str, Any] = dict(initial_state)
        yield json.dumps(
            {
                "type": "start",
                "snapshot": serialize_state(current_state),
            }
        ) + "\n"

        try:
            # We must use astream to prevent blocking the async loop. 
            async for event in research_graph.astream(current_state, stream_mode="updates"):
                if not isinstance(event, dict):
                    continue
                for node_name, update in event.items():
                    current_state = merge_update(current_state, update)
                    yield json.dumps(
                        {
                            "type": "update",
                            "node": node_name,
                            "update": update,
                            "snapshot": serialize_state(current_state),
                        }
                    ) + "\n"

            yield json.dumps(
                {
                    "type": "complete",
                    "snapshot": serialize_state(current_state),
                }
            ) + "\n"
        except Exception as exc:
            current_state = merge_update(
                current_state,
                {"error_log": [f"API stream error: {exc}"]},
            )
            yield json.dumps(
                {
                    "type": "error",
                    "message": str(exc),
                    "snapshot": serialize_state(current_state),
                }
            ) + "\n"

    return StreamingResponse(async_event_stream(), media_type="application/x-ndjson")
