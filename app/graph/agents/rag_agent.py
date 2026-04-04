from __future__ import annotations

from app.graph.state import ResearchState
from app.tools import retrieval_tool


def rag_node(state: ResearchState) -> dict:
    subtask = state.get("subtask", state["query"])
    subtask_id = state.get("subtask_id", subtask)
    try:
        results = retrieval_tool.retrieve_documents(subtask)
        if results and results[0].get("source") == "error":
            error_message = str(results[0].get("content", "RAG unavailable"))
            return {
                "rag_results": [],
                "completed_subtasks": [subtask_id],
                "error_log": [f"RAG agent error: {error_message}"],
                "agent_log": [f"RAG agent failed for '{subtask}'"],
            }

        relevant = [
            result for result in results if float(result.get("score", 999.0)) < 1.5
        ]
        return {
            "rag_results": relevant,
            "completed_subtasks": [subtask_id],
            "agent_log": [
                f"RAG agent completed: {len(relevant)} chunks for '{subtask}'"
            ],
        }
    except Exception as exc:
        return {
            "rag_results": [],
            "completed_subtasks": [subtask_id],
            "error_log": [f"RAG agent error: {exc}"],
            "agent_log": [f"RAG agent failed for '{subtask}'"],
        }
