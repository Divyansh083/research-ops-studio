import base64
from unittest.mock import patch
from fastapi.testclient import TestClient
from app.main import app

def test_config_endpoint_returns_runtime_payload():
    with patch("app.api.routers.system.list_datasets", return_value=[{"path": "C:/data/test.csv"}]), patch(
        "app.api.routers.system.sandbox_ready", return_value=True
    ):
        client = TestClient(app)
        response = client.get("/api/config")

    assert response.status_code == 200
    payload = response.json()
    assert payload["sandbox_ready"] is True
    assert payload["dataset_count"] == 1


def test_generate_dataset_endpoint_returns_latest_artifact():
    generated_dataset = {
        "path": "C:/data/generated/school_dataset_generated.csv",
        "status": "created",
        "summary": "Synthetic school performance dataset with attendance and subject scores.",
        "columns": ["StudentID", "StudentName"],
        "row_count": 10,
    }

    with patch(
        "app.api.routers.datasets.run_dataset_manager_request",
        return_value={
            "selected_dataset_path": generated_dataset["path"],
            "dataset_outputs": [generated_dataset],
            "agent_log": [],
            "error_log": [],
        },
    ), patch(
        "app.api.routers.datasets.list_datasets",
        return_value=[
            {
                "path": generated_dataset["path"],
                "name": "school_dataset_generated.csv",
                "group": "generated",
                "summary": generated_dataset["summary"],
                "row_count": 10,
                "columns": ["StudentID", "StudentName"],
            }
        ],
    ), patch("app.api.routers.datasets.discover_local_datasets", return_value=[]):
        client = TestClient(app)
        response = client.post(
            "/api/datasets/generate",
            json={"request": "Create a school dataset"},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_dataset_path"] == generated_dataset["path"]
    assert payload["dataset"]["status"] == "created"


def test_upload_dataset_endpoint_saves_base64_payload():
    file_bytes = b"Date,Close\n2026-03-01,100.0\n"
    file_payload = base64.b64encode(file_bytes).decode("utf-8")

    with patch(
        "app.api.routers.datasets.save_uploaded_dataset",
        return_value="C:/data/uploads/stock_prices.csv",
    ), patch(
        "app.api.routers.datasets.serialize_dataset",
        return_value={
            "path": "C:/data/uploads/stock_prices.csv",
            "name": "stock_prices.csv",
            "group": "uploads",
            "summary": "CSV dataset with 1 rows.",
            "row_count": 1,
            "columns": ["Date", "Close"],
        },
    ), patch(
        "app.api.routers.datasets.list_datasets",
        return_value=[],
    ):
        client = TestClient(app)
        response = client.post(
            "/api/datasets/upload",
            json={"filename": "stock_prices.csv", "content_base64": file_payload},
        )

    assert response.status_code == 200
    payload = response.json()
    assert payload["selected_dataset_path"].endswith("stock_prices.csv")


def test_research_stream_endpoint_yields_updates_and_complete_snapshot():
    stream_events = [
        {
            "supervisor": {
                "subtasks": [{"agent": "web_search", "subtask": "Compare approaches"}],
                "agent_log": ["Supervisor planned 1 subtasks"],
            }
        },
        {
            "synthesiser": {
                "final_report": "## Executive Summary\nDone",
                "agent_log": ["Synthesiser complete"],
            }
        },
    ]

    async def mock_astream(*args, **kwargs):
        for event in stream_events:
            yield event

    with patch("app.api.routers.research.discover_local_datasets", return_value=[]), patch(
        "app.api.routers.research.research_graph.astream", side_effect=mock_astream
    ):
        client = TestClient(app)
        with client.stream(
            "POST",
            "/api/research/stream",
            json={"query": "Compare RAG and fine-tuning"},
        ) as response:
            lines = [line for line in response.iter_lines() if line]

    assert response.status_code == 200
    assert any('"type": "update"' in line for line in lines)
    assert any('"type": "complete"' in line for line in lines)
