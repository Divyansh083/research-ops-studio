import pytest
from unittest.mock import MagicMock, patch
from app.graph.agents.supervisor import supervisor_node, _deduplicate_code_exec
from app.graph.state import ResearchState


def _make_state(query, dataset_outputs=None):
    """Helper to build a valid ResearchState dict."""
    return {
        "query": query,
        "subtasks": [],
        "search_results": [],
        "rag_results": [],
        "dataset_outputs": dataset_outputs or [],
        "code_outputs": [],
        "completed_subtasks": [],
        "summaries": [],
        "agent_log": [],
        "error_log": [],
    }


def test_supervisor_skips_redundant_creation_when_dataset_exists():
    """Verify that if a dataset is already created, the supervisor doesn't plan another creation subtask."""
    query = "Create a synthetic school dataset and then analyze the student grades."
    state = _make_state(query, dataset_outputs=[
        {
            "path": "data/generated/school.csv",
            "source_query": "Create a school dataset",
            "status": "created",
            "summary": "Synthetic school data",
            "columns": ["StudentID", "Grade"],
            "note": "success",
        }
    ])

    mock_llm_response = MagicMock()
    mock_llm_response.content = '[{"agent": "code_exec", "subtask": "Create a synthetic school dataset"}, {"agent": "code_exec", "subtask": "Analyze grades"}]'

    with patch("app.graph.agents.supervisor.get_llm", return_value=MagicMock(invoke=MagicMock(return_value=mock_llm_response))):
        result = supervisor_node(state)

    subtasks = result["subtasks"]
    for task in subtasks:
        desc = task["subtask"].lower()
        if "create" in desc and "dataset" in desc:
            assert "analyze" in desc or "address" in desc

    assert any("analyze" in t["subtask"].lower() for t in subtasks)


def test_supervisor_forces_analysis_on_mixed_query():
    """Verify that the forced code_exec task is focused on analysis when data is available."""
    query = "Analyze the stock data and plot a chart."
    state = _make_state(query, dataset_outputs=[
        {"status": "created", "path": "test.csv", "summary": "test", "columns": []}
    ])

    mock_llm_response = MagicMock()
    mock_llm_response.content = '[{"agent": "web_search", "subtask": "Search for stock news"}]'

    with patch("app.graph.agents.supervisor.get_llm", return_value=MagicMock(invoke=MagicMock(return_value=mock_llm_response))):
        result = supervisor_node(state)

    subtasks = result["subtasks"]
    assert "Analyze the dataset to fulfill" in subtasks[0]["subtask"]
    assert subtasks[0]["agent"] == "code_exec"


def test_supervisor_recognizes_reused_datasets():
    """Verify that the supervisor correctly identifies 'reused' datasets as available."""
    query = "Analyze the existing school data."
    state = _make_state(query, dataset_outputs=[
        {
            "path": "data/reused/school.csv",
            "source_query": "Previous query",
            "status": "reused",
            "summary": "Existing school data",
            "columns": ["ID", "Score"],
        }
    ])

    mock_llm_response = MagicMock()
    mock_llm_response.content = '[]'
    
    with patch("app.graph.agents.supervisor.get_llm", return_value=MagicMock(invoke=MagicMock(return_value=mock_llm_response))):
        result = supervisor_node(state)

    subtasks = result["subtasks"]
    assert any("Analyze the dataset to fulfill" in t["subtask"] for t in subtasks)


def test_deduplicate_code_exec_merges_multiple():
    """Verify that multiple code_exec subtasks are merged into one."""
    subtasks = [
        {"agent": "web_search", "subtask": "Search for school data trends"},
        {"agent": "code_exec", "subtask": "Calculate average attendance"},
        {"agent": "code_exec", "subtask": "Plot correlation between attendance and scores"},
    ]
    result = _deduplicate_code_exec(subtasks)

    code_tasks = [t for t in result if t["agent"] == "code_exec"]
    assert len(code_tasks) == 1
    assert "Calculate average attendance" in code_tasks[0]["subtask"]
    assert "Plot correlation" in code_tasks[0]["subtask"]


def test_deduplicate_code_exec_no_op_for_single():
    """Verify that a single code_exec subtask is left unchanged."""
    subtasks = [
        {"agent": "web_search", "subtask": "Search for school data trends"},
        {"agent": "code_exec", "subtask": "Comprehensive analysis"},
    ]
    result = _deduplicate_code_exec(subtasks)
    assert result == subtasks
