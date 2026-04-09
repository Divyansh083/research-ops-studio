from __future__ import annotations

from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langgraph.types import Send
from tenacity import retry, stop_after_attempt, wait_fixed

from app.graph.llm import get_llm
from app.graph.state import ResearchState, Subtask

SUPERVISOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior research planning agent. Decompose the user query into 3-5
focused, highly detailed subtasks that intelligently explore all facets of the query. For each subtask choose the best agent:
- "web_search": for recent events, news, current statistics, and general factual lookup
- "rag": for questions answerable from internal documents or the knowledge base
- "code_exec": for calculations, data analysis, charting, and numerical tasks

IMPORTANT RULES:
1. If the query asks to "Create" or "Generate" a dataset AND the context shows a dataset is ALREADY AVAILABLE, DO NOT plan another creation task.
2. Instead, focus "code_exec" tasks on analyzing, plotting, or processing the available dataset.
3. Do not include instructions like "Create a dataset" in "code_exec" subtasks if the data is already present.
4. NEVER create more than ONE "code_exec" subtask. If the query requires multiple analyses (e.g. statistics AND plotting), combine them into a SINGLE comprehensive "code_exec" subtask. Multiple code_exec subtasks produce redundant overlapping scripts.
5. Each subtask MUST be distinct from all other subtasks. Do not rephrase the same work as separate subtasks.

Return only a valid JSON array. No explanation and no markdown. Example:
[
  {{"agent": "web_search", "subtask": "Recent AI policy developments in India"}},
  {{"agent": "rag", "subtask": "EU AI Act key provisions and obligations"}},
  {{"agent": "code_exec", "subtask": "Load the dataset, calculate summary statistics, analyze correlations, and generate a comparison chart"}}
]""",
        ),
        ("human", "Query: {query}\n\nDataset Context: {dataset_context}"),
    ]
)


def _should_force_web_search(query: str, subtasks: list[Subtask]) -> bool:
    if any(task.get("agent") == "web_search" for task in subtasks):
        return False

    query_lower = query.lower()
    conceptual_markers = (
        "what is",
        "difference",
        "differences",
        "compare",
        "comparison",
        "vs",
        "versus",
        "explain",
        "overview",
    )
    return any(marker in query_lower for marker in conceptual_markers)


def _should_force_code_exec(query: str, subtasks: list[Subtask], dataset_available: bool) -> bool:
    if any(task.get("agent") == "code_exec" for task in subtasks):
        return False

    query_lower = query.lower()
    code_markers = (
        "write code",
        "write a python script",
        "python script",
        "python code",
        "execute code",
        "run code",
        "run a script",
        "execute a script",
        "load the csv",
        "load a csv",
        "dataframe",
    )
    has_code_signal = any(marker in query_lower for marker in code_markers)
    has_analysis_signal = any(verb in query_lower for verb in ("analyze", "analyse", "plot", "calculate", "compute")) and any(target in query_lower for target in ("dataset", "data", "csv", "table"))
    
    if not (has_code_signal or has_analysis_signal):
        return False

    # If dataset is already available, don't force the whole query (which might include "Create...").
    # Force a more focused analysis task instead.
    if dataset_available:
        return True
    return True

def _clean_subtasks(subtasks: list[Subtask], dataset_available: bool) -> list[Subtask]:
    if not dataset_available:
        return subtasks

    filtered = []
    creation_markers = ("create", "generate", "make", "build", "prepare")
    for task in subtasks:
        desc = task.get("subtask", "").lower()
        has_creation_verb = any(verb in desc for verb in creation_markers)
        has_dataset_target = any(target in desc for target in ("dataset", "csv", "dataframe", "table"))

        if has_creation_verb and has_dataset_target:
             # Transform creation subtask into analysis subtask if data exists
             task["agent"] = "code_exec"
             task["subtask"] = f"Analyze the generated dataset to address: {task.get('subtask')}"
        filtered.append(task)
    return filtered


def _deduplicate_code_exec(subtasks: list[Subtask]) -> list[Subtask]:
    """Merge all code_exec subtasks into a single comprehensive task.

    Multiple code_exec subtasks lead to redundant, overlapping scripts.
    Combining them into one ensures a single cohesive analysis script.
    """
    code_tasks = [t for t in subtasks if t.get("agent") == "code_exec"]
    other_tasks = [t for t in subtasks if t.get("agent") != "code_exec"]

    if len(code_tasks) <= 1:
        return subtasks

    # Merge all code_exec descriptions into one combined subtask
    combined_description = "; ".join(
        t.get("subtask", "") for t in code_tasks if t.get("subtask")
    )
    merged_task: Subtask = {
        "agent": "code_exec",
        "subtask": combined_description,
    }
    other_tasks.append(merged_task)
    return other_tasks


def _should_drop_code_exec(query: str) -> bool:
    query_lower = query.lower()
    conceptual_markers = (
        "what is",
        "what are",
        "which",
        "should i",
        "should we",
        "recommend",
        "suggest",
        "best",
        "top",
        "how does",
        "how do",
        "why does",
        "why do",
        "difference",
        "differences",
        "compare",
        "comparison",
        "vs",
        "versus",
        "explain",
        "overview",
        "describe",
        "impact of",
        "effect of",
        "relationship between",
        "key trends",
        "factors",
        "pros and cons",
        "advantages",
        "disadvantages",
    )
    numeric_markers = (
        "calculate",
        "compute",
        "plot",
        "chart",
        "graph",
        "statistics",
        "numeric",
        "numerical",
        "benchmark",
        "dataset",
        "csv",
        "table",
        "load the",
        "analyze the dataset",
        "analyse the dataset",
        "write code",
        "python script",
        "execute code",
    )
    return any(marker in query_lower for marker in conceptual_markers) and not any(
        marker in query_lower for marker in numeric_markers
    )


@retry(stop=stop_after_attempt(2), wait=wait_fixed(1))
def _decompose_query(query: str, dataset_outputs: list[dict] | None = None) -> list[Subtask]:
    llm = get_llm()
    
    dataset_context = "No dataset currently available."
    dataset_available = False
    if dataset_outputs:
        valid_datasets = [d for d in dataset_outputs if d.get("status") in {"created", "reused"}]
        if valid_datasets:
            dataset_available = True
            dataset_context = "The following dataset was just created and is ready for analysis:\n"
            for d in valid_datasets:
                dataset_context += f"- Path: {d.get('path')}\n  Summary: {d.get('summary')}\n  Columns: {', '.join(d.get('columns', []))}\n"

    response = llm.invoke(SUPERVISOR_PROMPT.format_messages(query=query, dataset_context=dataset_context))
    result = JsonOutputParser().parse(str(response.content))
    if not isinstance(result, list):
        raise ValueError("LLM did not return a JSON array")

    subtasks: list[Subtask] = []
    for item in result[:4]:
        if not isinstance(item, dict):
            continue
        agent = str(item.get("agent", "web_search")).strip() or "web_search"
        subtask = str(item.get("subtask", query)).strip() or query
        subtasks.append({"agent": agent, "subtask": subtask})

    subtasks = _clean_subtasks(subtasks, dataset_available)

    if _should_drop_code_exec(query):
        subtasks = [task for task in subtasks if task.get("agent") != "code_exec"]

    if _should_force_code_exec(query, subtasks, dataset_available):
        forced_task = query
        if dataset_available:
            forced_task = f"Analyze the dataset to fulfill: {query}"
        subtasks.insert(0, {"agent": "code_exec", "subtask": forced_task})
        subtasks = subtasks[:4]

    if _should_force_web_search(query, subtasks):
        subtasks.insert(0, {"agent": "web_search", "subtask": query})
        subtasks = subtasks[:4]

    # Merge any duplicate code_exec subtasks into one comprehensive task
    subtasks = _deduplicate_code_exec(subtasks)

    if not subtasks:
        raise ValueError("No valid subtasks were generated")
    return subtasks

def supervisor_node(state: ResearchState) -> dict:
    query = state["query"]
    dataset_outputs = state.get("dataset_outputs", [])
    try:
        subtasks = _decompose_query(query, dataset_outputs)
        return {
            "subtasks": subtasks,
            "agent_log": [f"Supervisor planned {len(subtasks)} subtasks"],
        }
    except Exception as exc:
        fallback = [{"agent": "web_search", "subtask": query}]
        return {
            "subtasks": fallback,
            "agent_log": ["Supervisor fallback triggered; using a single web search task"],
            "error_log": [f"Supervisor planning error: {exc}"],
        }


def dispatch_subtasks(state: ResearchState) -> list[Send]:
    agent_map = {
        "web_search": "web_search_agent",
        "rag": "rag_agent",
        "code_exec": "code_exec_agent",
    }

    sends: list[Send] = []
    for index, task in enumerate(state.get("subtasks", []), start=1):
        agent_key = task.get("agent", "web_search")
        node_name = agent_map.get(agent_key, "web_search_agent")
        sends.append(
            Send(
                node_name,
                {
                    "query": state["query"],
                    "subtask": task.get("subtask", state["query"]),
                    "subtask_id": f"task-{index}",
                    "available_datasets": state.get("available_datasets", []),
                    "selected_dataset_path": state.get("selected_dataset_path"),
                },
            )
        )
    return sends
