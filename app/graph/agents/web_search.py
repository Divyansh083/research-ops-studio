from __future__ import annotations

from app.graph.state import ResearchState
from app.tools import search_tool


def web_search_node(state: ResearchState) -> dict:
    subtask = state.get("subtask", state["query"])
    subtask_id = state.get("subtask_id", subtask)
    try:
        results = search_tool.duckduckgo_search(subtask)
        if results and results[0].get("title", "").lower() == "search error":
            error_message = results[0].get("snippet", "Unknown search error")
            return {
                "search_results": [],
                "completed_subtasks": [subtask_id],
                "error_log": [f"WebSearch agent error: {error_message}"],
                "agent_log": [f"WebSearch agent failed for '{subtask}'"],
            }
        return {
            "search_results": results,
            "completed_subtasks": [subtask_id],
            "agent_log": [
                f"WebSearch agent completed: {len(results)} results for '{subtask}'"
            ],
        }
    except Exception as exc:
        return {
            "search_results": [],
            "completed_subtasks": [subtask_id],
            "error_log": [f"WebSearch agent error: {exc}"],
            "agent_log": [f"WebSearch agent failed for '{subtask}'"],
        }
