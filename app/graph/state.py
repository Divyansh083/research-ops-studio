from __future__ import annotations

import operator
from typing import Annotated, Optional, TypedDict

try:
    from typing import NotRequired
except ImportError:  # pragma: no cover - Python < 3.11 compatibility
    from typing_extensions import NotRequired


class Subtask(TypedDict):
    agent: str
    subtask: str


class SearchResult(TypedDict):
    title: str
    snippet: str
    url: str


class RagResult(TypedDict):
    content: str
    source: str
    score: float


class CodeOutput(TypedDict):
    code: str
    output: str
    error: Optional[str]
    status: str
    note: Optional[str]
    dataset_path: Optional[str]
    dataset_source_path: Optional[str]
    artifacts: list[str]


class DatasetArtifact(TypedDict):
    path: Optional[str]
    source_query: str
    status: str
    summary: str
    note: Optional[str]
    row_count: Optional[int]
    columns: list[str]


class ResearchState(TypedDict):
    query: str
    subtasks: list[Subtask]
    search_results: Annotated[list[SearchResult], operator.add]
    rag_results: Annotated[list[RagResult], operator.add]
    dataset_outputs: Annotated[list[DatasetArtifact], operator.add]
    code_outputs: Annotated[list[CodeOutput], operator.add]
    completed_subtasks: Annotated[list[str], operator.add]
    summaries: Annotated[list[str], operator.add]
    final_report: Optional[str]
    agent_log: Annotated[list[str], operator.add]
    error_log: Annotated[list[str], operator.add]
    subtask: NotRequired[str]
    subtask_id: NotRequired[str]
    available_datasets: NotRequired[list[str]]
    selected_dataset_path: NotRequired[Optional[str]]
