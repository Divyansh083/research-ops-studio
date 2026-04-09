from __future__ import annotations

import re
from typing import Any
from pathlib import Path

import pandas as pd
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from tenacity import retry, stop_after_attempt, wait_fixed

from app.graph.llm import get_llm
from app.graph.state import ResearchState
from app.tools.dataset_registry import (
    build_dataset_csv,
    choose_dataset_for_query,
    discover_local_datasets,
    find_generated_dataset,
    generate_dataset_filename,
    inspect_dataset_file,
    save_generated_dataset,
)

DATASET_CREATION_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a dataset preparation agent.
Create a small realistic CSV dataset that can be used for local testing and analysis.

Return only a valid JSON object with this shape:
{
  "filename": "short_file_name.csv",
  "summary": "one sentence describing the dataset",
  "columns": ["col1", "col2"],
  "rows": [
    ["value1", 123],
    ["value2", 456]
  ]
}

Rules:
- Output only JSON. No markdown.
- The dataset must be self-contained and synthetic.
- Use 15 to 40 rows. Ensure the data is highly varied and rich in features.
- Keep values realistic for the request.
- Prefer CSV-friendly scalar values only.
- If the request implies time series data, include a Date column with ISO dates.
- If the request implies stock data, include Date, Open, High, Low, Close, and Volume columns.
""",
        ),
        ("human", "User request: {query}"),
    ]
)

DATASET_CREATION_MARKERS = (
    "create a dataset",
    "generate a dataset",
    "build a dataset",
    "make a dataset",
    "prepare a dataset",
    "create csv",
    "generate csv",
    "sample dataset",
    "mock dataset",
    "synthetic dataset",
    "dummy dataset",
    "dummy csv",
)

DATASET_CREATION_VERBS = ("create", "generate", "build", "make", "prepare")

DATASET_REQUEST_MARKERS = (
    "dataset",
    "csv",
    "dataframe",
    "table",
    "school",
    "student",
    "attendance",
    "grade",
    "stock",
    "price",
    "sales",
    "revenue",
    "inventory",
    "orders",
    "customer",
    "weather",
    "transactions",
)

CODE_OR_ANALYSIS_MARKERS = (
    "write code",
    "python script",
    "python code",
    "execute",
    "run",
    "analyse",
    "analyze",
    "plot",
    "chart",
    "calculate",
    "compute",
    "statistics",
    "trend",
    "summary statistics",
)

POST_CREATION_WORK_MARKERS = (
    "execute",
    "run",
    "analyse",
    "analyze",
    "plot",
    "chart",
    "calculate",
    "compute",
    "statistics",
    "trend",
    "explain",
    "summarise",
    "summarize",
)


# =============================================================================
# 🔷 UTILITIES (Merged from dataset_agent.py)
# =============================================================================


def extract_json(text: str) -> Any | None:
    text = str(text).strip()

    if "```" in text:
        parts = text.split("```")
        if len(parts) >= 2:
            text = parts[1]
            if text.startswith("json"):
                text = text[4:]

    text = text.strip()

    try:
        return JsonOutputParser().parse(text)
    except Exception:
        # Fallback to regex for array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            try:
                return JsonOutputParser().parse(match.group())
            except Exception:
                pass
        # Fallback to regex for object
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return JsonOutputParser().parse(match.group())
            except Exception:
                pass
    return None


def _strip_code_fences(raw_text: str) -> str:
    text = raw_text.strip()
    if not text.startswith("```"):
        return text

    lines = text.splitlines()
    if lines:
        lines = lines[1:]
    if lines and lines[-1].strip() == "```":
        lines = lines[:-1]
    return "\n".join(lines).strip()


# =============================================================================
# 🔷 PIPELINE CORE
# =============================================================================


def generate_dataset_raw(llm: Any, user_prompt: str) -> Any | None:
    prompt = f"""
    Generate a dataset based on this request:

    {user_prompt}

    Rules:
    - Return ONLY a JSON array of objects
    - No explanation
    - Each object should have the requested columns
    - Use realistic data
    - 15 to 30 rows
    """
    response = llm.invoke(prompt)
    return extract_json(str(response.content))


def validate_dataset_list(data: Any) -> tuple[bool, Any]:
    if data is None:
        return False, "Data is None"

    if not isinstance(data, list):
        return False, "Data must be a list"

    if len(data) == 0:
        return False, "Dataset cannot be empty"

    if not all(isinstance(row, dict) for row in data):
        return False, "All rows must be dictionaries"

    # Check all rows have the same keys
    first_keys = set(data[0].keys())
    for row in data[1:]:
        if set(row.keys()) != first_keys:
            return False, "All rows must have the same columns across all records"

    return True, data


def fix_dataset_raw(llm: Any, bad_data: Any, error_message: str, user_prompt: str) -> str:
    prompt = f"""
You generated an INVALID dataset.

USER REQUEST:
{user_prompt}

INVALID DATA:
{bad_data}

ERROR:
{error_message}

Fix the dataset STRICTLY.

RULES:
- Return ONLY valid JSON array
- Ensure all rows have equal columns
- Valid data types
- 15 to 30 rows
"""
    response = llm.invoke(prompt)
    return str(response.content)


def dataset_pipeline(llm: Any, user_prompt: str, max_retries: int = 2) -> dict[str, Any]:
    """Unified dataset generation pipeline with validation and self-correction."""
    data = generate_dataset_raw(llm, user_prompt)

    for attempt in range(max_retries):
        if data is None:
            data = generate_dataset_raw(llm, user_prompt)
            continue

        is_valid, result = validate_dataset_list(data)

        if is_valid:
            df = pd.DataFrame(result)
            return {
                "status": "success",
                "data": result,
                "rows": len(df),
                "columns": list(df.columns),
            }

        error_message = str(result)
        fixed_raw = fix_dataset_raw(llm, data, error_message, user_prompt)
        data = extract_json(fixed_raw)

        # Handle nested wrapper if LLM adds it
        if isinstance(data, dict) and "rows" in data:
            data = data["rows"]

    return {"status": "failed", "reason": "Could not generate valid tabular dataset after retries."}


# =============================================================================
# 🔷 MANAGER NODE
# =============================================================================


def _is_dataset_creation_request(query_lower: str) -> bool:
    if any(marker in query_lower for marker in DATASET_CREATION_MARKERS):
        return True
    has_creation_verb = any(verb in query_lower for verb in DATASET_CREATION_VERBS)
    has_dataset_target = any(marker in query_lower for marker in ("dataset", "csv", "table", "dataframe"))
    return has_creation_verb and has_dataset_target


def query_requires_dataset_manager(state: ResearchState) -> bool:
    query_lower = state["query"].lower()

    # Always route if the user explicitly asks to create/generate a dataset
    if _is_dataset_creation_request(query_lower):
        return True

    # ── Guard: Conceptual queries should NEVER trigger dataset_manager ──
    # If the query is asking a research/conceptual question, even if it mentions
    # data-related words like "student" or "attendance", it does NOT need a dataset.
    conceptual_markers = (
        "what are",
        "what is",
        "how does",
        "how do",
        "why does",
        "why do",
        "explain",
        "describe",
        "overview",
        "compare",
        "difference",
        "impact of",
        "effect of",
        "relationship between",
        "key trends",
        "factors",
    )
    is_conceptual = any(marker in query_lower for marker in conceptual_markers)

    # Explicit data-action phrases that DO require a dataset
    explicit_data_actions = (
        "analyze the dataset",
        "analyse the dataset",
        "analyze the csv",
        "analyse the csv",
        "plot the dataset",
        "plot the csv",
        "load the csv",
        "load the dataset",
        "run code on",
        "execute code on",
        "write a script",
        "python script",
        "write code",
    )
    has_explicit_action = any(phrase in query_lower for phrase in explicit_data_actions)

    # If conceptual AND no explicit data action, skip dataset_manager
    if is_conceptual and not has_explicit_action:
        return False

    # Otherwise, use the standard signal check
    has_dataset_signal = any(marker in query_lower for marker in DATASET_REQUEST_MARKERS)
    has_code_signal = any(marker in query_lower for marker in CODE_OR_ANALYSIS_MARKERS)
    return bool(has_dataset_signal and has_code_signal)


def query_is_dataset_creation_only(query: str) -> bool:
    query_lower = query.lower()
    if not _is_dataset_creation_request(query_lower):
        return False
    return not any(marker in query_lower for marker in POST_CREATION_WORK_MARKERS)


def _coerce_rows(raw_rows: list[Any], width: int) -> list[list[Any]]:
    rows: list[list[Any]] = []
    for raw_row in raw_rows[:40]:
        if not isinstance(raw_row, list):
            continue
        coerced = [value for value in raw_row[:width]]
        if len(coerced) == width:
            rows.append(coerced)
    return rows


def _validate_dataset_spec(spec: dict[str, Any]) -> dict[str, Any]:
    columns = [str(col).strip() for col in spec.get("columns", []) if str(col).strip()]
    if not columns:
        raise ValueError("Dataset spec missing columns")

    rows = _coerce_rows(spec.get("rows", []), len(columns))
    if not rows:
        raise ValueError("Dataset spec missing valid rows")

    filename = str(spec.get("filename", "generated_dataset.csv")).strip() or "generated_dataset.csv"
    summary = str(spec.get("summary", "Agent-generated dataset")).strip()
    return {
        "filename": filename,
        "summary": summary,
        "columns": columns,
        "rows": rows,
    }


def _build_fallback_dataset_spec(query: str) -> dict[str, Any]:
    query_lower = query.lower()
    # Simple hardcoded fallback templates for resilience
    if "stock" in query_lower or "price" in query_lower:
        rows = [["2026-03-02", 101.10, 101.50, 99.80, 101.10, 1200000]]
        for i in range(1, 10):
            rows.append([f"2026-03-0{2+i}", 101.1+i, 102.3+i, 100.7+i, 101.9+i, 1100000+i*1000])
        return {
            "filename": "stock_prices_fallback.csv",
            "summary": "Synthetic daily stock prices.",
            "columns": ["Date", "Open", "High", "Low", "Close", "Volume"],
            "rows": rows,
        }

    if "school" in query_lower or "student" in query_lower:
        rows = [
            ["S001", "Aarav Mehta", 6, "A", 96.4, 88, 91, 90],
            ["S002", "Diya Sharma", 6, "A", 94.1, 92, 89, 93],
            ["S003", "Kabir Singh", 6, "B", 89.5, 76, 82, 79],
            ["S004", "Ananya Iyer", 6, "B", 98.2, 95, 94, 96],
            ["S005", "Ishaan Roy", 6, "A", 91.8, 81, 85, 84],
            ["S006", "Saanvi Gupta", 6, "B", 95.7, 89, 88, 91],
            ["S007", "Arjun Verma", 6, "A", 93.4, 84, 86, 87],
            ["S008", "Myra Kapoor", 6, "B", 97.1, 93, 92, 94],
            ["S009", "Reyansh Das", 6, "A", 90.2, 78, 81, 80],
            ["S010", "Zoya Khan", 6, "B", 94.9, 90, 89, 92],
        ]
        return {
            "filename": "school_dataset_fallback.csv",
            "summary": "Synthetic school performance dataset with attendance and subject scores.",
            "columns": [
                "StudentID",
                "StudentName",
                "GradeLevel",
                "Section",
                "AttendanceRate",
                "MathScore",
                "ScienceScore",
                "EnglishScore",
            ],
            "rows": rows,
        }

    # Default fallback
    columns = ["Date", "Category", "Value", "Notes"]
    rows = [[f"2026-03-0{i}", "A", 10 + i, "Synthetic data"] for i in range(1, 11)]
    return {
        "filename": "generated_dataset_fallback.csv",
        "summary": "Synthetic general-purpose dataset.",
        "columns": columns,
        "rows": rows,
    }


def _build_reuse_artifact(
    path: str,
    query: str,
    summary: str,
    note: str,
    columns: list[str] | None = None,
    row_count: int | None = None,
) -> dict[str, Any]:
    return {
        "path": path,
        "source_query": query,
        "status": "reused",
        "summary": summary,
        "note": note,
        "row_count": row_count,
        "columns": columns or [],
    }


def dataset_manager_node(state: ResearchState) -> dict:
    query = state["query"]
    llm = get_llm()

    try:
        selected_dataset_path = state.get("selected_dataset_path")

        # ✅ Reuse explicitly selected dataset
        if selected_dataset_path and Path(str(selected_dataset_path)).exists():
            selected_path = str(selected_dataset_path)
            if not _is_dataset_creation_request(query.lower()):
                inspected = inspect_dataset_file(selected_path)
                return {
                    "selected_dataset_path": selected_path,
                    "dataset_outputs": [
                        _build_reuse_artifact(
                            selected_path,
                            query,
                            str(inspected.get("summary", "Reused local dataset.")),
                            "Reused dataset previously selected in terminal.",
                            columns=list(inspected.get("columns", [])),
                            row_count=inspected.get("row_count"),
                        )
                    ],
                    "agent_log": [f"DatasetManager reused '{selected_path}'"],
                }

        # ✅ Check for compatible dataset in available_datasets
        available_datasets = state.get("available_datasets", [])
        if available_datasets:
            best_local_path = choose_dataset_for_query(query, available_datasets)
            if best_local_path:
                inspected = inspect_dataset_file(best_local_path)
                return {
                    "selected_dataset_path": best_local_path,
                    "dataset_outputs": [
                        _build_reuse_artifact(
                            best_local_path,
                            query,
                            str(inspected.get("summary", "Reused compatible local dataset.")),
                            "Found compatible dataset in search path.",
                            columns=list(inspected.get("columns", [])),
                            row_count=inspected.get("row_count"),
                        )
                    ],
                    "agent_log": [f"DatasetManager matched available dataset: '{best_local_path}'"],
                }

        # ✅ Attempt LLM Generation Pipeline
        try:
            result = dataset_pipeline(llm, query)
            if result["status"] == "success":
                file_content = build_dataset_csv(result.get("columns", []), result.get("data", []))
                dataset_entry = save_generated_dataset(
                    filename=generate_dataset_filename(query),
                    content=file_content,
                    source_query=query,
                    summary=result.get("summary", "LLM-generated synthetic dataset"),
                    columns=result.get("columns", []),
                    row_count=result.get("rows", 0),
                )
                final_path = str(dataset_entry["path"])
                return {
                    "selected_dataset_path": final_path,
                    "dataset_outputs": [
                        {
                            "path": final_path,
                            "source_query": query,
                            "status": "created",
                            "summary": str(dataset_entry.get("summary", "Successfully generated dataset")),
                            "note": "Generated via self-correcting LLM pipeline",
                            "row_count": dataset_entry.get("row_count"),
                            "columns": dataset_entry.get("columns"),
                        }
                    ],
                    "agent_log": [f"DatasetManager created '{final_path}' via LLM pipeline"],
                }
            raise Exception(result.get("reason", "Pipeline failure"))

        except Exception as e:
            # 🛑 Hardcoded Fallback
            spec = _build_fallback_dataset_spec(query)
            csv_content = build_dataset_csv(spec["columns"], spec["rows"])
            dataset_entry = save_generated_dataset(
                filename=spec["filename"],
                content=csv_content,
                source_query=query,
                summary=spec["summary"],
                columns=spec["columns"],
                row_count=len(spec["rows"]),
            )
            created_path = str(dataset_entry["path"])
            return {
                "selected_dataset_path": created_path,
                "dataset_outputs": [
                    {
                        "path": created_path,
                        "source_query": query,
                        "status": "created",
                        "summary": str(dataset_entry.get("summary")),
                        "note": f"Fallback due to: {str(e)}",
                        "row_count": len(spec["rows"]),
                        "columns": spec["columns"],
                    }
                ],
                "agent_log": [f"DatasetManager created fallback '{created_path}'"],
            }

    except Exception as exc:
        return {
            "dataset_outputs": [{"status": "error", "note": str(exc)}],
            "error_log": [f"DatasetManager critical failure: {exc}"],
            "agent_log": ["DatasetManager failed completely"],
        }


def run_dataset_manager_request(
    query: str,
    available_datasets: list[str] | None = None,
    selected_dataset_path: str | None = None,
) -> dict:
    initial_state: ResearchState = {
        "query": query,
        "subtasks": [],
        "search_results": [],
        "rag_results": [],
        "dataset_outputs": [],
        "code_outputs": [],
        "summaries": [],
        "final_report": None,
        "agent_log": [],
        "error_log": [],
        "available_datasets": available_datasets or discover_local_datasets(),
        "selected_dataset_path": selected_dataset_path,
    }
    return dataset_manager_node(initial_state)
