import json
from pathlib import Path
from unittest.mock import patch

import pytest

from app.tools.dataset_registry import (
    choose_dataset_for_query,
    discover_local_datasets,
    find_generated_dataset,
    generate_dataset_filename,
    get_generated_dataset_dir,
    prepare_dataset_for_code_exec,
    save_generated_dataset,
)


def test_prepare_dataset_for_code_exec_copies_to_sandbox(tmp_path):
    source_dataset = tmp_path / "stock_prices.csv"
    source_dataset.write_text("Date,Close\n2026-03-01,100.0\n", encoding="utf-8")
    sandbox_workspace = tmp_path / "sandbox_workspace"
    sandbox_workspace.mkdir()

    with patch("app.tools.dataset_registry.get_sandbox_workspace", return_value=sandbox_workspace):
        prepared_path = prepare_dataset_for_code_exec(str(source_dataset))

    assert prepared_path.endswith("stock_prices.csv")
    assert (sandbox_workspace / "datasets" / "stock_prices.csv").exists()


def test_choose_dataset_for_query_prefers_relevant_dataset(tmp_path):
    stock_path = tmp_path / "stock_prices.csv"
    stock_path.write_text("Date,Close\n2026-03-01,100.0\n", encoding="utf-8")
    sales_path = tmp_path / "sales_data.csv"
    sales_path.write_text("Date,Revenue\n2026-03-01,1000\n", encoding="utf-8")

    selected = choose_dataset_for_query(
        "Write code to analyze the stock price dataset",
        [str(sales_path), str(stock_path)],
    )
    assert selected == str(stock_path.resolve())


def test_choose_dataset_for_query_does_not_reuse_unrelated_single_dataset(tmp_path):
    stock_path = tmp_path / "stock_prices.csv"
    stock_path.write_text("Date,Close\n2026-03-01,100.0\n", encoding="utf-8")

    selected = choose_dataset_for_query(
        "Create a sales dataset for local testing",
        [str(stock_path)],
    )
    assert selected is None


def test_find_generated_dataset_ignores_incompatible_cached_dataset(tmp_path):
    data_root = tmp_path / "data"
    generated_dir = data_root / "generated"
    generated_dir.mkdir(parents=True)
    generic_dataset = generated_dir / "generated_dataset.csv"
    generic_dataset.write_text(
        "Date,Category,Value,Notes\n2026-03-01,A,10,Baseline\n",
        encoding="utf-8",
    )
    manifest_path = generated_dir / "manifest.json"
    manifest_path.write_text(
        json.dumps(
            [
                {
                    "signature": "create a school dataset and then write and execute a python script to analyze it.",
                    "path": str(generic_dataset.resolve()),
                    "source_query": "Create a School dataset and then write and execute a Python script to analyze it.",
                    "summary": "Synthetic general-purpose tabular dataset for local testing.",
                    "columns": ["Date", "Category", "Value", "Notes"],
                    "row_count": 1,
                }
            ]
        ),
        encoding="utf-8",
    )

    with patch("app.tools.dataset_registry.settings.dataset_root_dir", str(data_root)):
        match = find_generated_dataset(
            "Create a School dataset and then write and execute a Python script to analyze it."
        )

    assert match is None


def test_discover_local_datasets_excludes_generated_manifest(tmp_path):
    data_root = tmp_path / "data"
    generated_dir = data_root / "generated"
    generated_dir.mkdir(parents=True)
    dataset_path = generated_dir / "example.csv"
    dataset_path.write_text("Date,Value\n2026-03-01,1\n", encoding="utf-8")
    manifest_path = generated_dir / "manifest.json"
    manifest_path.write_text("[]", encoding="utf-8")

    with patch("app.tools.dataset_registry.settings.dataset_root_dir", str(data_root)):
        datasets = discover_local_datasets()

    assert str(dataset_path.resolve()) in datasets
    assert str(manifest_path.resolve()) not in datasets


def test_generate_filename_title_case():
    filename = generate_dataset_filename("create realistic commerce orders")
    assert filename == "Create_Realistic_Commerce_Orders.csv"


def test_save_generated_dataset_uses_generated_folder(tmp_path):
    data_root = tmp_path / "data"

    with patch("app.tools.dataset_registry.settings.dataset_root_dir", str(data_root)):
        content = "a,b\n1,2\n"
        entry = save_generated_dataset(
            filename="test.csv",
            content=content,
            source_query="test query",
            summary="test",
            columns=["a", "b"],
            row_count=1,
        )

        generated_dir = get_generated_dataset_dir()

        assert Path(entry["path"]).resolve().parent == generated_dir.resolve()
        assert (generated_dir / "test.csv").exists()
