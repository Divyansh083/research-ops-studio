import operator
from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage

from app.graph.state import ResearchState


def get_initial_state(query: str = "Test query") -> ResearchState:
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
    }


@patch("app.graph.agents.supervisor._decompose_query")
@patch("app.tools.search_tool.duckduckgo_search")
@patch("app.graph.agents.summariser.get_llm")
@patch("app.graph.agents.synthesiser.get_llm")
def test_graph_full_run(
    mock_synth_llm,
    mock_summariser_llm,
    mock_search,
    mock_decompose_query,
):
    mock_decompose_query.return_value = [
        {"agent": "web_search", "subtask": "Test subtask"}
    ]
    mock_search.return_value = [
        {"title": "Test", "snippet": "Test result", "url": "http://test.com"}
    ]
    mock_summariser_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(content="Intermediate summary")
    )
    mock_synth_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(content="## Test Report\nTest content.")
    )

    from app.graph.graph import build_graph

    graph = build_graph()
    result = graph.invoke(get_initial_state())

    assert result["final_report"] is not None
    assert len(result["agent_log"]) > 0
    assert result["subtasks"][0]["agent"] == "web_search"


def test_state_operator_add_merging():
    a = [{"result": 1}]
    b = [{"result": 2}]
    merged = operator.add(a, b)
    assert len(merged) == 2
    assert merged[0]["result"] == 1
    assert merged[1]["result"] == 2


@patch("app.graph.agents.supervisor.get_llm")
def test_supervisor_forces_web_search_for_comparison_queries(mock_get_llm):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content='[{"agent": "rag", "subtask": "Explain RAG documents"}, {"agent": "code_exec", "subtask": "Plot the comparison"}]'
        )
    )

    from app.graph.agents.supervisor import _decompose_query

    subtasks = _decompose_query("What are the differences between RAG and fine-tuning?")
    assert subtasks[0]["agent"] == "web_search"
    assert all(task["agent"] != "code_exec" for task in subtasks)


@patch("app.graph.agents.supervisor.get_llm")
def test_supervisor_forces_code_exec_for_explicit_coding_requests(mock_get_llm):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content='[{"agent": "web_search", "subtask": "Find stock analysis guides"}]'
        )
    )

    from app.graph.agents.supervisor import _decompose_query

    subtasks = _decompose_query(
        "Write and execute a Python script to analyze the available stock price dataset"
    )
    assert any(task["agent"] == "code_exec" for task in subtasks)


@patch("app.graph.agents.synthesiser.get_llm")
def test_synthesiser_falls_back_to_model_knowledge(mock_get_llm):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(content="## Executive Summary\nFallback answer")
    )

    from app.graph.agents.synthesiser import synthesiser_node

    result = synthesiser_node(get_initial_state("What is RAG versus fine-tuning?"))
    assert "Fallback answer" in result["final_report"]


def test_route_from_start_uses_dataset_manager_for_dataset_queries():
    from app.graph.graph import route_from_start

    state = get_initial_state(
        "Write and execute a Python script to analyze a stock price dataset"
    )
    assert route_from_start(state) == "dataset_manager_agent"


def test_route_after_dataset_manager_skips_supervisor_for_creation_only_queries():
    from app.graph.graph import route_after_dataset_manager

    state = get_initial_state("Create a stock price dataset for local testing")
    assert route_after_dataset_manager(state) == "summariser"
