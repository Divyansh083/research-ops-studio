from __future__ import annotations

from langgraph.graph import END, START, StateGraph
from app.graph.state import ResearchState

from app.graph.agents.code_exec import code_exec_node
from app.graph.agents.dataset_manager import (
    dataset_manager_node,
    query_is_dataset_creation_only,
    query_requires_dataset_manager,
)
from app.graph.agents.rag_agent import rag_node
from app.graph.agents.summariser import summariser_node
from app.graph.agents.supervisor import dispatch_subtasks, supervisor_node
from app.graph.agents.synthesiser import synthesiser_node
from app.graph.agents.web_search import web_search_node


def fan_in_node(state: ResearchState) -> dict:
    completed = len(state.get("completed_subtasks", []))
    expected = len(state.get("subtasks", []))
    return {
        "agent_log": [f"Fan-in progress: {completed}/{expected} subtasks completed"],
    }


def route_after_fan_in(state: ResearchState):
    completed = len(state.get("completed_subtasks", []))
    expected = len(state.get("subtasks", []))
    if completed >= expected:
        return "summariser"
    # Even with partial completion, synthesize what we have rather than dropping results.
    # The fan_in_node logs progress, so incomplete subtasks are tracked.
    return "summariser"


def route_from_start(state: ResearchState):
    if query_requires_dataset_manager(state):
        return "dataset_manager_agent"
    return "supervisor"


def route_after_dataset_manager(state: ResearchState):
    if query_is_dataset_creation_only(state["query"]):
        return "summariser"
    return "supervisor"


def build_graph():
    graph = StateGraph(ResearchState)

    graph.add_node("dataset_manager_agent", dataset_manager_node)
    graph.add_node("supervisor", supervisor_node)
    graph.add_node("web_search_agent", web_search_node)
    graph.add_node("rag_agent", rag_node)
    graph.add_node("code_exec_agent", code_exec_node)
    graph.add_node("fan_in", fan_in_node)
    graph.add_node("summariser", summariser_node)
    graph.add_node("synthesiser", synthesiser_node)

    graph.add_conditional_edges(START, route_from_start)
    graph.add_conditional_edges("dataset_manager_agent", route_after_dataset_manager)
    graph.add_conditional_edges("supervisor", dispatch_subtasks)
    graph.add_edge("web_search_agent", "fan_in")
    graph.add_edge("rag_agent", "fan_in")
    graph.add_edge("code_exec_agent", "fan_in")
    graph.add_conditional_edges("fan_in", route_after_fan_in)
    graph.add_edge("summariser", "synthesiser")
    graph.add_edge("synthesiser", END)

    return graph.compile()


research_graph = build_graph()
