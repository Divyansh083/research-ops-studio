from __future__ import annotations

import ast
import re
from pathlib import Path
import textwrap

from langchain_core.prompts import ChatPromptTemplate

from app.graph.llm import get_llm
from app.graph.state import ResearchState
from app.sandbox import validate_code, get_policy
from app.tools.dataset_registry import (
    choose_dataset_for_query,
    inspect_dataset_file,
    prepare_dataset_for_code_exec,
)
from app.sandbox.executor import execute_code

CODE_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a data analysis agent. Write Python code to answer the subtask.
You can use any standard library plus pandas, numpy, and matplotlib.
Do not assume any other third-party libraries are available.
Print the answer and any key findings to stdout.
You are encouraged to generate relevant files (CSV, PDF, PNG, JSON) in the current directory if they help the research.
Never invent or simulate data. If the task does not provide data, do not fabricate an example.
If a local dataset is provided, use it.
Return only executable Python code.""",
        ),
        ("human", "Subtask: {subtask}\n\nDataset context:\n{dataset_context}"),
    ]
)

CODE_FIX_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a code debugging agent. The Python script below was executed and
produced an error. Fix the script so it runs successfully.

IMPORTANT DEBUGGING RULES:
1. If the error is `ValueError: 'yerr' must not contain negative values` or similar matplotlib bounds errors, the calculated error values are negative (e.g. tracking distance to a min/max outside the current result). Use `np.abs(yerr)` or `np.maximum(0, yerr)` to guarantee all error margins are positive float values.
2. If the error is a `KeyError`, verify you are using the exact column names provided in the dataset context.
3. If the error is `FileNotFoundError`, strictly use the provided `DATASET_PATH` without prepending directories.
4. Do NOT attempt to remove the sandbox safe preamble at the top of the file. Leave the imports intact.
5. Do NOT use eval(), exec(), __import__(), subprocess, os.system(), or any blocked operations.
6. Only use safe libraries: pandas, numpy, matplotlib, and standard lib.

Return ONLY the corrected, raw Python code. Do not wrap it in markdown formatting or ```python fences. Provide zero explanation.""",
        ),
        (
            "human",
            """Original subtask: {subtask}

Failing code:
{code}

Error output:
{error}

Security warnings:
{security_warnings}

Dataset context:
{dataset_context}""",
        ),
    ]
)


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


def _longest_valid_python_prefix(code: str) -> tuple[str, str | None]:
    normalized = code.strip()
    if normalized.lower().startswith("python\n"):
        normalized = normalized.split("\n", 1)[1].strip()

    try:
        ast.parse(normalized)
        return normalized, None
    except SyntaxError:
        pass

    lines = normalized.splitlines()
    for index in range(len(lines) - 1, 0, -1):
        candidate = "\n".join(lines[:index]).rstrip()
        if not candidate:
            continue
        try:
            ast.parse(candidate)
            return (
                candidate,
                "Trimmed trailing non-code text from the generated script before execution",
            )
        except SyntaxError:
            continue

    return normalized, None


def _combine_notes(*notes: str | None) -> str | None:
    cleaned = [note for note in notes if note]
    if not cleaned:
        return None
    return " | ".join(cleaned)


def _is_computational_request(text: str) -> bool:
    text_lower = text.lower()
    
    # If the subtask is ONLY about creation/mocking without analysis, skip it.
    # DatasetManager already handles the initial creation.
    creation_only = any(marker in text_lower for marker in ("create a dataset", "generate a dataset", "make a dataset"))
    has_analysis = any(marker in text_lower for marker in ("plot", "calculate", "analyze", "analyse", "statistic", "trend", "chart"))
    
    if creation_only and not has_analysis:
        return False
        
    markers = (
        "calculate",
        "compute",
        "plot",
        "chart",
        "graph",
        "table",
        "statistics",
        "numeric",
        "numerical",
        "trend",
        "benchmark",
        "data",
        "csv",
        "analyze numbers",
        "analyse numbers",
        "dataframe",
    )
    return any(marker in text_lower for marker in markers)


def _choose_dataset_path(state: ResearchState, subtask: str) -> str | None:
    selected = state.get("selected_dataset_path")
    if selected and Path(selected).exists():
        return str(Path(selected).resolve())

    available = [
        str(Path(path).resolve())
        for path in state.get("available_datasets", [])
        if Path(path).exists()
    ]
    return choose_dataset_for_query(f"{state.get('query', '')} {subtask}", available)


def _request_needs_dataset_analysis(text: str) -> bool:
    text_lower = text.lower()
    return any(
        marker in text_lower
        for marker in (
            "analyse",
            "analyze",
            "analysis",
            "summarize",
            "summarise",
            "statistics",
            "trend",
            "dataset",
        )
    )


def _build_dataset_context(
    state: ResearchState,
    subtask: str,
) -> tuple[str, str | None, str | None, str | None, dict | None]:
    dataset_source_path = _choose_dataset_path(state, subtask)
    available = [
        str(Path(path).resolve())
        for path in state.get("available_datasets", [])
        if Path(path).exists()
    ]

    if dataset_source_path:
        inspected = inspect_dataset_file(dataset_source_path)
        prepared_path = prepare_dataset_for_code_exec(dataset_source_path)
        schema_lines = [
            "Use this local dataset path exactly:",
            prepared_path,
            "Do not ask the user for another path and do not invent a filename.",
            f"Dataset summary: {inspected.get('summary', 'N/A')}",
        ]
        if inspected.get("row_count") is not None:
            schema_lines.append(f"Dataset rows: {inspected.get('row_count')}")
        columns = list(inspected.get("columns", []))
        if columns:
            schema_lines.append(f"Exact columns: {', '.join(columns)}")
        return (
            "\n".join(schema_lines),
            prepared_path,
            dataset_source_path,
            (
                "Prepared the dataset for sandbox execution. "
                f"Source: {dataset_source_path} | Sandbox copy: {prepared_path}"
            ),
            inspected,
        )

    if available:
        listing = "\n".join(f"- {path}" for path in available)
        return (
            "Local datasets are available, but no single best match was selected yet.\n"
            "If one clearly matches the task, use it. Otherwise keep the script runnable "
            "with a DATASET_PATH variable and a file-existence check.\n"
            f"{listing}",
            None,
            None,
            None,
            None,
        )

    return (
        "No local dataset path is available in the app context. If the task needs a dataset, "
        "write code with a DATASET_PATH variable and a clear file-existence check.",
        None,
        None,
        None,
        None,
    )


def _validate_code_security(code: str) -> tuple[bool, str | None, list[str]]:
    """Run the sandbox AST security validator against generated code.

    Returns (is_safe, block_reason_or_none, warning_messages).
    """
    policy = get_policy()
    result = validate_code(code, policy)
    warnings = [v.detail for v in result.warnings]
    if not result.is_safe:
        block_reason = "; ".join(v.detail for v in result.blocking_violations)
        return False, block_reason, warnings
    return True, None, warnings




def _contains_placeholder_columns(code: str) -> bool:
    code_lower = code.lower()
    placeholder_markers = (
        "column_name",
        "your_column",
        "target_column",
        "feature_column",
        "label_column",
        "replace_with",
    )
    return any(marker in code_lower for marker in placeholder_markers)


def _is_too_shallow_for_analysis(code: str) -> bool:
    code_lower = code.lower()
    load_markers = ("read_csv(", "read_excel(", "read_json(", "read_parquet(")
    analysis_markers = (
        "describe(",
        "groupby(",
        ".mean(",
        ".median(",
        ".agg(",
        "value_counts(",
        "select_dtypes(",
        ".corr(",
        "sort_values(",
        "rolling(",
        "plot(",
    )
    if not any(marker in code_lower for marker in load_markers):
        return False
    return not any(marker in code_lower for marker in analysis_markers)


def _dataset_reader_expression(dataset_path: str) -> str:
    suffix = Path(dataset_path).suffix.lower()
    if suffix == ".csv":
        return "pd.read_csv(DATASET_PATH)"
    if suffix in {".xlsx", ".xls"}:
        return "pd.read_excel(DATASET_PATH)"
    if suffix == ".json":
        return "pd.read_json(DATASET_PATH)"
    if suffix == ".parquet":
        return "pd.read_parquet(DATASET_PATH)"
    return "pd.read_csv(DATASET_PATH)"


def _build_schema_aware_analysis_script(
    dataset_path: str,
    subtask: str,
    dataset_info: dict | None,
) -> str:
    normalized_path = str(Path(dataset_path).resolve()).replace("\\", "/")
    columns = [str(column) for column in (dataset_info or {}).get("columns", [])]
    query_lower = subtask.lower()
    school_markers = ("school", "student", "attendance", "grade", "class")
    school_score_columns = [
        column
        for column in ("MathScore", "ScienceScore", "EnglishScore")
        if column in columns
    ]
    is_school_dataset = any(marker in query_lower for marker in school_markers) or bool(
        school_score_columns
    )
    reader_expression = _dataset_reader_expression(dataset_path)
    lines = [
        "import pandas as pd",
        "import numpy as np",
        "import matplotlib.pyplot as plt",
        "",
        f'DATASET_PATH = r"{normalized_path}"',
        "",
        f"df = {reader_expression}",
        "print(f'ROWS {len(df)}')",
        "print('COLUMNS', list(df.columns))",
        "print('HEAD')",
        "print(df.head().to_string(index=False))",
        "",
        "numeric_columns = df.select_dtypes(include=[np.number]).columns.tolist()",
        "print('NUMERIC_COLUMNS', numeric_columns)",
        "if numeric_columns:",
        "    print('NUMERIC_SUMMARY')",
        "    print(df[numeric_columns].describe().round(2).to_string())",
        "else:",
        "    print('NUMERIC_SUMMARY none')",
        "",
        "missing_counts = df.isna().sum()",
        "print('MISSING_VALUES')",
        "print(missing_counts.to_string())",
    ]

    if "Date" in columns:
        lines.extend(
            [
                "",
                "df['Date'] = pd.to_datetime(df['Date'], errors='coerce')",
                "dated_df = df.dropna(subset=['Date']).sort_values('Date')",
                "if not dated_df.empty and numeric_columns:",
                "    preferred_trend_columns = [col for col in ['Close', 'Revenue', 'Value'] if col in dated_df.columns]",
                "    trend_column = preferred_trend_columns[0] if preferred_trend_columns else numeric_columns[0]",
                "    start_value = float(dated_df[trend_column].iloc[0])",
                "    end_value = float(dated_df[trend_column].iloc[-1])",
                "    delta = end_value - start_value",
                "    direction = 'upward' if delta > 0 else ('downward' if delta < 0 else 'flat')",
                "    print(f'TREND {trend_column}: {direction} ({start_value:.2f} -> {end_value:.2f})')",
            ]
        )

    if is_school_dataset:
        lines.extend(
            [
                "",
                "score_columns = [col for col in ['MathScore', 'ScienceScore', 'EnglishScore'] if col in df.columns]",
                "if score_columns:",
                "    df['AverageScore'] = df[score_columns].mean(axis=1).round(2)",
                "    print('AVERAGE_SCORE_BY_STUDENT')",
                "    student_columns = [col for col in ['StudentName', 'StudentID', 'GradeLevel', 'Section', 'AverageScore'] if col in df.columns]",
                "    print(df[student_columns].sort_values('AverageScore', ascending=False).to_string(index=False))",
                "    group_column = 'GradeLevel' if 'GradeLevel' in df.columns else ('Section' if 'Section' in df.columns else None)",
                "    if group_column is not None:",
                "        print(f'AVERAGE_SCORE_BY_{group_column.upper()}')",
                "        print(df.groupby(group_column)['AverageScore'].mean().round(2).to_string())",
                "if 'AttendanceRate' in df.columns:",
                "    print('ATTENDANCE_SUMMARY')",
                "    print(df['AttendanceRate'].describe().round(2).to_string())",
            ]
        )

    lines.extend(
        [
            "",
            "print('ANALYSIS_COMPLETE')",
        ]
    )
    return "\n".join(lines)


def _inject_dataset_path(code: str, dataset_path: str | None) -> tuple[str, str | None]:
    if not dataset_path:
        return code, None

    normalized_path = str(Path(dataset_path).resolve()).replace("\\", "/")
    updated = code
    note: str | None = None

    assignment_pattern = re.compile(r"(?m)^DATASET_PATH\s*=\s*.*$")
    if assignment_pattern.search(updated):
        updated = assignment_pattern.sub(
            f'DATASET_PATH = r"{normalized_path}"',
            updated,
            count=1,
        )
        note = "Updated the generated script to use the selected dataset path"
        return updated, note

    for pattern in (
        re.compile(r"((?:\w+\.)?read_csv\(\s*)(r?['\"][^'\"]+['\"])", re.IGNORECASE),
        re.compile(r"((?:\w+\.)?read_excel\(\s*)(r?['\"][^'\"]+['\"])", re.IGNORECASE),
        re.compile(r"((?:\w+\.)?read_json\(\s*)(r?['\"][^'\"]+['\"])", re.IGNORECASE),
        re.compile(r"((?:\w+\.)?read_parquet\(\s*)(r?['\"][^'\"]+['\"])", re.IGNORECASE),
        re.compile(r"(open\(\s*)(r?['\"][^'\"]+['\"])", re.IGNORECASE),
    ):
        updated, count = pattern.subn(
            lambda match: f'{match.group(1)}r"{normalized_path}"',
            updated,
            count=1,
        )
        if count:
            note = "Rewrote the generated script to use the selected dataset path"
            return updated, note

    return updated, None


def _looks_like_runtime_error(output: str) -> bool:
    output_lower = output.lower()
    return (
        "traceback" in output_lower 
        or "error" in output_lower 
        or "exception" in output_lower
        or "exited with code" in output_lower
    )


def code_exec_node(state: ResearchState) -> dict:
    subtask = state.get("subtask", state["query"])
    subtask_id = state.get("subtask_id", subtask)
    if not _is_computational_request(subtask):
        return {
            "code_outputs": [],
            "completed_subtasks": [subtask_id],
            "agent_log": [f"CodeExec skipped for '{subtask}' because no computation was requested"],
        }

    try:
        llm = get_llm()
        (
            dataset_context,
            dataset_path,
            dataset_source_path,
            dataset_context_note,
            dataset_info,
        ) = _build_dataset_context(state, subtask)
        response = llm.invoke(
            CODE_PROMPT.format_messages(
                subtask=subtask,
                dataset_context=dataset_context,
            )
        )
        code = _strip_code_fences(str(response.content))
        if not code:
            raise ValueError("Generated code was empty")
        code, cleanup_note = _longest_valid_python_prefix(code)
        code, dataset_note = _inject_dataset_path(code, dataset_path)
        schema_fallback_note: str | None = None
        if dataset_path and dataset_info and (
            _contains_placeholder_columns(code)
            or (_request_needs_dataset_analysis(subtask) and _is_too_shallow_for_analysis(code))
        ):
            code = _build_schema_aware_analysis_script(dataset_path, subtask, dataset_info)
            schema_fallback_note = (
                "Replaced the model-generated script with a schema-aware analysis script "
                "based on the actual dataset"
            )

        # ── Sandbox Security Validation (replaces ad-hoc checks) ───────
        is_safe, block_reason, security_warnings = _validate_code_security(code)
        security_note: str | None = None

        if security_warnings:
            security_note = f"Security warnings: {'; '.join(security_warnings)}"

        if not is_safe:
            message = f"CodeExec blocked by security policy: {block_reason}"
            return {
                "code_outputs": [
                    {
                        "code": code,
                        "output": "",
                        "error": message,
                        "status": "blocked",
                        "note": _combine_notes(
                            "Code blocked by sandbox security policy",
                            block_reason,
                            dataset_context_note,
                            dataset_note,
                            cleanup_note,
                            schema_fallback_note,
                        ),
                        "dataset_path": dataset_path,
                        "dataset_source_path": dataset_source_path,
                        "artifacts": [],
                    }
                ],
                "completed_subtasks": [subtask_id],
                "error_log": [message],
                "agent_log": [
                    f"CodeExec BLOCKED for '{subtask}': {block_reason}",
                ],
            }

        try:
            ast.parse(code)
        except SyntaxError as exc:
            message = f"CodeExec generated invalid Python and was skipped: {exc}"
            return {
                "code_outputs": [
                    {
                        "code": code,
                        "output": "",
                        "error": message,
                        "status": "error",
                        "note": _combine_notes(
                            "Generated code was not executable Python",
                            dataset_context_note,
                            dataset_note,
                            cleanup_note,
                            schema_fallback_note,
                        ),
                        "dataset_path": dataset_path,
                        "dataset_source_path": dataset_source_path,
                        "artifacts": [],
                    }
                ],
                "completed_subtasks": [subtask_id],
                "error_log": [message],
                "agent_log": [f"CodeExec agent failed for '{subtask}'"],
            }

        # We pass skip_validation=True because we already validated above.
        _exec_res = execute_code(code, skip_validation=True)
        if _exec_res.blocked and "auto-setup" in (_exec_res.blocked_reason or ""):
            raise RuntimeError(_exec_res.blocked_reason)
        result = _exec_res.to_dict()
        output = result["output"]
        artifacts = result.get("artifacts", [])

        MAX_RETRIES = 2
        retry_count = 0

        # Format security context for the fix prompt
        security_ctx = "\n".join(security_warnings) if security_warnings else "None"

        # Loop retries if we hit runtime errors
        while _looks_like_runtime_error(output) and retry_count < MAX_RETRIES:
            retry_count += 1
            try:
                fix_response = llm.invoke(
                    CODE_FIX_PROMPT.format_messages(
                        subtask=subtask,
                        code=code,
                        error=output[-3000:],
                        security_warnings=security_ctx,
                        dataset_context=dataset_context,
                    )
                )
                fixed_code = _strip_code_fences(str(fix_response.content))
                fixed_code, _ = _longest_valid_python_prefix(fixed_code)
                fixed_code, _ = _inject_dataset_path(fixed_code, dataset_path)

                # Validate the fix against security policy too
                fix_safe, fix_block, fix_warns = _validate_code_security(fixed_code)
                if not fix_safe:
                    # LLM generated unsafe fix — abort retry
                    break

                _retry_exec_res = execute_code(fixed_code, skip_validation=True)
                if _retry_exec_res.blocked and "auto-setup" in (_retry_exec_res.blocked_reason or ""):
                    raise RuntimeError(_retry_exec_res.blocked_reason)
                retry_result = _retry_exec_res.to_dict()
                output = retry_result["output"]
                artifacts = retry_result.get("artifacts", [])
                code = fixed_code
                security_warnings = fix_warns
            except Exception:
                break  # If retry invocation itself fails, break loop

        if _looks_like_runtime_error(output):
            return {
                "code_outputs": [
                    {
                        "code": code,
                        "output": output,
                        "error": output,
                        "status": "error",
                        "note": _combine_notes(
                            f"Execution failed (after {retry_count} retries)",
                            security_note,
                            dataset_context_note,
                            dataset_note,
                            cleanup_note,
                            schema_fallback_note,
                        ),
                        "dataset_path": dataset_path,
                        "dataset_source_path": dataset_source_path,
                        "artifacts": artifacts,
                    }
                ],
                "completed_subtasks": [subtask_id],
                "error_log": [f"CodeExec agent runtime error: {output[-1000:]}"],
                "agent_log": [f"CodeExec agent failed for '{subtask}'"],
            }

        status_msg = f"Execution succeeded after {retry_count} retries" if retry_count > 0 else "Execution succeeded"
        return {
            "code_outputs": [
                {
                    "code": code,
                    "output": output,
                    "error": None,
                    "status": "success",
                    "note": _combine_notes(
                        status_msg,
                        security_note,
                        dataset_context_note,
                        dataset_note,
                        cleanup_note,
                        schema_fallback_note,
                    ),
                    "dataset_path": dataset_path,
                    "dataset_source_path": dataset_source_path,
                    "artifacts": artifacts,
                }
            ],
            "completed_subtasks": [subtask_id],
            "agent_log": [f"CodeExec agent completed for '{subtask}'"],
        }
    except Exception as exc:
        return {
            "code_outputs": [
                {
                    "code": "",
                    "output": "",
                    "error": str(exc),
                    "status": "error",
                    "note": "Execution failed before code completed",
                    "dataset_path": None,
                    "dataset_source_path": None,
                    "artifacts": [],
                }
            ],
            "completed_subtasks": [subtask_id],
            "error_log": [f"CodeExec agent error: {exc}"],
            "agent_log": [f"CodeExec agent failed for '{subtask}'"],
        }
