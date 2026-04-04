from unittest.mock import MagicMock, patch

from langchain_core.messages import AIMessage


def make_state(subtask: str = "Test subtask") -> dict:
    return {
        "query": "Test query",
        "subtask": subtask,
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


@patch("app.tools.search_tool.duckduckgo_search")
def test_web_search_agent_success(mock_search):
    mock_search.return_value = [{"title": "T", "snippet": "S", "url": "http://u.com"}]

    from app.graph.agents.web_search import web_search_node

    result = web_search_node(make_state())
    assert len(result["search_results"]) == 1
    assert len(result["agent_log"]) == 1


@patch("app.tools.search_tool.duckduckgo_search")
def test_web_search_agent_error_handling(mock_search):
    mock_search.return_value = [{"title": "Search error", "snippet": "Network error", "url": ""}]

    from app.graph.agents.web_search import web_search_node

    result = web_search_node(make_state())
    assert len(result["error_log"]) == 1
    assert result["search_results"] == []


@patch("app.tools.retrieval_tool.retrieve_documents")
def test_rag_agent_success(mock_retrieve):
    mock_retrieve.return_value = [{"content": "chunk", "source": "doc.pdf", "score": 0.3}]

    from app.graph.agents.rag_agent import rag_node

    result = rag_node(make_state())
    assert len(result["rag_results"]) == 1


@patch("app.graph.agents.code_exec.execute_code")
@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_agent_failure_capture(mock_get_llm, mock_run_python):
    mock_get_llm.return_value.invoke = MagicMock(return_value=AIMessage(content="print('hi')"))
    mock_run_python.side_effect = RuntimeError("boom")

    from app.graph.agents.code_exec import code_exec_node

    result = code_exec_node(make_state("Calculate the average score"))
    assert result["code_outputs"][0]["status"] == "error"
    assert result["code_outputs"][0]["error"] == "boom"
    assert len(result["error_log"]) == 1


def test_code_exec_skips_non_computational_requests():
    from app.graph.agents.code_exec import code_exec_node

    result = code_exec_node(make_state("Explain the difference between RAG and fine-tuning"))
    assert result["code_outputs"] == []
    assert "skipped" in result["agent_log"][0].lower()


@patch("app.graph.agents.code_exec.execute_code")
@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_allows_synthetic_data_with_warning(mock_get_llm, mock_run_python):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content="import numpy as np\nnp.random.seed(0)\nprint('demo')"
        )
    )
    mock_run_python.return_value = MagicMock(blocked=False, blocked_reason=None, to_dict=lambda: {"output": "demo", "artifacts": [], "plot_files": []})

    from app.graph.agents.code_exec import code_exec_node

    result = code_exec_node(make_state("Plot the comparison"))
    # Synthetic data is now ALLOWED (policy doesn't block it), not skipped
    assert result["code_outputs"][0]["status"] == "success"


@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_blocks_network_dependent_code(mock_get_llm):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content="import pandas as pd\nimport requests\nrequests.get('https://example.com')"
        )
    )

    from app.graph.agents.code_exec import code_exec_node

    result = code_exec_node(make_state("Plot the statistics from the website"))
    # Network imports are now BLOCKED by security policy
    assert result["code_outputs"][0]["status"] == "blocked"
    assert "security policy" in result["error_log"][0].lower()


@patch("app.graph.agents.code_exec.execute_code")
@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_handles_missing_local_files_at_runtime(mock_get_llm, mock_run_python):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content="import pandas as pd\ndf = pd.read_csv('stock_data.csv')\nprint(df.head())"
        )
    )
    # Simulates runtime FileNotFoundError
    mock_run_python.return_value = MagicMock(blocked=False, blocked_reason=None, to_dict=lambda: {"output": "Traceback: FileNotFoundError: stock_data.csv", "artifacts": [], "plot_files": []})

    from app.graph.agents.code_exec import code_exec_node

    result = code_exec_node(make_state("Plot the stock data from csv"))
    # Missing files are now caught at runtime, not pre-skipped
    assert result["code_outputs"][0]["status"] == "error"


@patch("app.graph.agents.code_exec.execute_code")
@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_trims_trailing_prose_before_execution(mock_get_llm, mock_run_python):
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content=(
                "import pandas as pd\n"
                "print('done')\n"
                "Note that you should replace 'stock_prices.csv' with your actual file path."
            )
        )
    )
    mock_run_python.return_value = MagicMock(blocked=False, blocked_reason=None, to_dict=lambda: {"output": "done", "plot_files": []})

    from app.graph.agents.code_exec import code_exec_node

    result = code_exec_node(make_state("Calculate summary statistics from the dataset"))
    assert result["code_outputs"][0]["status"] == "success"
    assert "Note that you should replace" not in result["code_outputs"][0]["code"]
    assert "Trimmed trailing non-code text" in result["code_outputs"][0]["note"]


@patch("app.graph.agents.code_exec.prepare_dataset_for_code_exec")
@patch("app.graph.agents.code_exec.execute_code")
@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_uses_selected_dataset_path(
    mock_get_llm,
    mock_run_python,
    mock_prepare_dataset,
    tmp_path,
):
    dataset_path = tmp_path / "stock_prices.csv"
    dataset_path.write_text("Date,Close\n2026-03-01,101.2\n", encoding="utf-8")
    sandbox_dataset_path = tmp_path / "sandbox_stock_prices.csv"
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content=(
                "import pandas as pd\n"
                "df = pd.read_csv('stock_data.csv')\n"
                "print(df.head())"
            )
        )
    )
    mock_prepare_dataset.return_value = str(sandbox_dataset_path)
    mock_run_python.return_value = MagicMock(blocked=False, blocked_reason=None, to_dict=lambda: {"output": "ok", "plot_files": []})

    from app.graph.agents.code_exec import code_exec_node

    state = make_state("Load the dataset and print the first rows")
    state["available_datasets"] = [str(dataset_path)]
    state["selected_dataset_path"] = str(dataset_path)
    result = code_exec_node(state)

    executed_code = mock_run_python.call_args.args[0]
    assert str(sandbox_dataset_path).replace("\\", "/") in executed_code
    assert result["code_outputs"][0]["status"] == "success"
    assert "dataset path" in result["code_outputs"][0]["note"].lower()
    assert result["code_outputs"][0]["dataset_source_path"] == str(dataset_path)
    assert result["code_outputs"][0]["dataset_path"] == str(sandbox_dataset_path)


@patch("app.graph.agents.summariser.get_llm")
def test_summariser_no_results(mock_llm):
    from app.graph.agents.summariser import summariser_node

    result = summariser_node(make_state())
    assert "No results found" in result["summaries"][0]


@patch("app.graph.agents.summariser.get_llm")
def test_summariser_success(mock_get_llm):
    mock_get_llm.return_value.invoke = MagicMock(return_value=AIMessage(content="Short summary"))

    from app.graph.agents.summariser import summariser_node

    state = make_state()
    state["search_results"] = [
        {"title": "Result", "snippet": "Useful snippet", "url": "http://example.com"}
    ]
    result = summariser_node(state)
    assert result["summaries"][0] == "Short summary"


@patch("app.graph.agents.dataset_manager.find_generated_dataset", return_value=None)
@patch("app.graph.agents.dataset_manager.discover_local_datasets")
def test_dataset_manager_reuses_matching_dataset(
    mock_discover_local_datasets,
    mock_find_generated_dataset,
):
    dataset_path = "data/sample_data/stock_prices.csv"
    mock_discover_local_datasets.return_value = [dataset_path]

    from app.graph.agents.dataset_manager import dataset_manager_node       

    state = make_state("Write and execute a Python script to analyze the stock price dataset")
    state["query"] = "Write and execute a Python script to analyze the stock price dataset"
    state["available_datasets"] = [dataset_path]
    state["selected_dataset_path"] = dataset_path
    result = dataset_manager_node(state)

    assert result["selected_dataset_path"] == dataset_path
@patch("app.graph.agents.dataset_manager.find_generated_dataset", return_value=None)
@patch("app.graph.agents.dataset_manager.save_generated_dataset")
@patch("app.graph.agents.dataset_manager.discover_local_datasets")
@patch("app.graph.agents.dataset_manager.dataset_pipeline")
@patch("app.graph.agents.dataset_manager.get_llm")
def test_dataset_manager_creates_dataset_when_missing(
    mock_get_llm,
    mock_dataset_pipeline,
    mock_discover_local_datasets,
    mock_save_generated_dataset,
    mock_find_generated_dataset,
    tmp_path,
):
    created_path = tmp_path / "generated_stock_prices.csv"
    mock_discover_local_datasets.side_effect = [[], [str(created_path)]]
    mock_save_generated_dataset.return_value = {
        "path": str(created_path),
        "summary": "Synthetic stock dataset",
        "columns": ["Date", "Close"],
        "row_count": 2,
    }
    mock_dataset_pipeline.return_value = {
        "status": "success",
        "file": str(created_path),
        "summary": "Synthetic stock dataset",
        "columns": ["Date", "Close"],
        "data": [{"Date": "2026-03-01", "Close": 101.2}, {"Date": "2026-03-02", "Close": 102.4}],
        "rows": 2
    }

    from app.graph.agents.dataset_manager import dataset_manager_node

    state = make_state("Create a stock price dataset for testing")
    state["query"] = "Create a stock price dataset for testing"
    result = dataset_manager_node(state)

    assert result["selected_dataset_path"] == str(created_path)
    assert result["dataset_outputs"][0]["status"] == "created"


@patch("app.graph.agents.dataset_manager.find_generated_dataset", return_value=None)
@patch("app.graph.agents.dataset_manager.save_generated_dataset")
@patch("app.graph.agents.dataset_manager.discover_local_datasets")
@patch("app.graph.agents.dataset_manager.dataset_pipeline")
@patch("app.graph.agents.dataset_manager.get_llm")
def test_dataset_manager_uses_school_template_for_school_queries(
    mock_get_llm,
    mock_dataset_pipeline,
    mock_discover_local_datasets,
    mock_save_generated_dataset,
    mock_find_generated_dataset,
    tmp_path,
):
    created_path = tmp_path / "school_dataset_generated.csv"
    mock_discover_local_datasets.side_effect = [[], [str(created_path)]]
    mock_dataset_pipeline.return_value = {"status": "failed", "reason": "Simulated LLM failure"}
    mock_save_generated_dataset.return_value = {
        "path": str(created_path),
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
        "row_count": 10,
    }

    from app.graph.agents.dataset_manager import dataset_manager_node

    state = make_state("Create a School dataset and then write and execute a Python script to analyze it.")
    state["query"] = "Create a School dataset and then write and execute a Python script to analyze it."
    result = dataset_manager_node(state)

    assert result["selected_dataset_path"] == str(created_path)
    assert result["dataset_outputs"][0]["status"] == "created"
    assert result["dataset_outputs"][0]["summary"].lower().startswith("synthetic school")
    save_kwargs = mock_save_generated_dataset.call_args.kwargs
    assert save_kwargs["filename"].endswith(".csv")
    assert any(term in save_kwargs["filename"].lower() for term in ["generated", "school"])
    assert any("student" in c.lower() for c in save_kwargs["columns"])


@patch("app.graph.agents.dataset_manager.find_generated_dataset", return_value=None)
@patch("app.graph.agents.dataset_manager.save_generated_dataset")
@patch("app.graph.agents.dataset_manager.discover_local_datasets")
@patch("app.graph.agents.dataset_manager.dataset_pipeline")
@patch("app.graph.agents.dataset_manager.get_llm")
def test_run_dataset_manager_request_returns_created_dataset(
    mock_get_llm,
    mock_dataset_pipeline,
    mock_discover_local_datasets,
    mock_save_generated_dataset,
    mock_find_generated_dataset,
    tmp_path,
):
    created_path = tmp_path / "school_dataset_generated.csv"
    mock_discover_local_datasets.side_effect = [[], [], [str(created_path)]]
    mock_dataset_pipeline.return_value = {"status": "failed", "reason": "Simulated LLM failure"}
    mock_save_generated_dataset.return_value = {
        "path": str(created_path),
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
        "row_count": 10,
    }

    from app.graph.agents.dataset_manager import run_dataset_manager_request

    result = run_dataset_manager_request(
        "Create a school dataset with attendance and subject scores for 10 students"
    )

    assert result["selected_dataset_path"] == str(created_path)
    assert result["dataset_outputs"][0]["status"] == "created"


@patch("app.graph.agents.code_exec.prepare_dataset_for_code_exec")
@patch("app.graph.agents.code_exec.execute_code")
@patch("app.graph.agents.code_exec.get_llm")
def test_code_exec_replaces_placeholder_column_analysis_with_schema_aware_script(
    mock_get_llm,
    mock_run_python,
    mock_prepare_dataset,
    tmp_path,
):
    dataset_path = tmp_path / "school_dataset.csv"
    dataset_path.write_text(
        (
            "StudentID,StudentName,GradeLevel,Section,AttendanceRate,MathScore,ScienceScore,EnglishScore\n"
            "S001,Aarav Mehta,6,A,96.4,88,91,90\n"
            "S002,Diya Sharma,6,A,94.1,92,89,93\n"
        ),
        encoding="utf-8",
    )
    sandbox_dataset_path = tmp_path / "sandbox_school_dataset.csv"
    mock_get_llm.return_value.invoke = MagicMock(
        return_value=AIMessage(
            content=(
                "import pandas as pd\n"
                "df = pd.read_csv(DATASET_PATH)\n"
                "print(df['column_name'].mean())"
            )
        )
    )
    mock_prepare_dataset.return_value = str(sandbox_dataset_path)
    mock_run_python.return_value = MagicMock(blocked=False, blocked_reason=None, to_dict=lambda: {"output": "ROWS 2\nANALYSIS_COMPLETE", "plot_files": []})

    from app.graph.agents.code_exec import code_exec_node

    state = make_state("Create a School dataset and then write and execute a Python script to analyze it.")
    state["query"] = "Create a School dataset and then write and execute a Python script to analyze it."
    state["selected_dataset_path"] = str(dataset_path)
    state["available_datasets"] = [str(dataset_path)]
    result = code_exec_node(state)

    executed_code = mock_run_python.call_args.args[0]
    assert result["code_outputs"][0]["status"] == "success"
    assert "column_name" not in executed_code
    assert "AverageScore" in executed_code
    assert "AttendanceRate" in executed_code
    assert "schema-aware" in result["code_outputs"][0]["note"].lower()
