from typing import Any
from app.graph.state import ResearchState

LIST_APPEND_KEYS = {
    "search_results",
    "rag_results",
    "dataset_outputs",
    "code_outputs",
    "completed_subtasks",
    "summaries",
    "agent_log",
    "error_log",
}

def make_initial_state(
    query: str,
    available_datasets: list[str],
    selected_dataset_path: str | None,
) -> ResearchState:
    return {
        "query": query,
        "subtasks": [],
        "search_results": [],
        "rag_results": [],
        "dataset_outputs": [],
        "code_outputs": [],
        "completed_subtasks": [],
        "summaries": [],
        "final_report": None,
        "agent_log": [],
        "error_log": [],
        "available_datasets": available_datasets,
        "selected_dataset_path": selected_dataset_path,
    }

def merge_update(state: dict[str, Any], update: dict[str, Any]) -> dict[str, Any]:
    merged = dict(state)
    for key, value in update.items():
        if key in LIST_APPEND_KEYS:
            merged.setdefault(key, [])
            merged[key].extend(value)
        else:
            merged[key] = value
    return merged

def serialize_state(state: dict[str, Any]) -> dict[str, Any]:
    serialized_code_outputs = []
    for item in state.get("code_outputs", []):
        entry = dict(item)
        entry.setdefault("plot_files", [])
        serialized_code_outputs.append(entry)

    return {
        "query": state.get("query", ""),
        "subtasks": state.get("subtasks", []),
        "search_results": state.get("search_results", []),
        "rag_results": state.get("rag_results", []),
        "dataset_outputs": state.get("dataset_outputs", []),
        "code_outputs": serialized_code_outputs,
        "completed_subtasks": state.get("completed_subtasks", []),
        "summaries": state.get("summaries", []),
        "final_report": state.get("final_report"),
        "agent_log": state.get("agent_log", []),
        "error_log": state.get("error_log", []),
        "selected_dataset_path": state.get("selected_dataset_path"),
        "available_datasets": state.get("available_datasets", []),
    }
