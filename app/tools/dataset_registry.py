from __future__ import annotations

import csv
import json
import re
import shutil
from io import StringIO
from pathlib import Path
from typing import Any

from app.core.config import settings
from app.sandbox.environment import get_sandbox_workspace

DATASET_EXTENSIONS = {".csv", ".xlsx", ".xls", ".json", ".parquet", ".pdf", ".docx", ".doc"}
MANIFEST_FILENAME = "manifest.json"
DATASET_DOMAIN_MARKERS = {
    "stock": {"stock", "stocks", "price", "prices", "close", "volume", "market"},
    "sales": {"sales", "sale", "revenue", "product", "units", "region"},
    "weather": {"weather", "temperature", "rainfall", "humidity", "forecast", "city"},
    "employee": {"employee", "employees", "salary", "hr", "department", "performance"},
    "orders": {"order", "orders", "inventory", "customer", "customers", "shipment"},
    "school": {
        "school",
        "schools",
        "student",
        "students",
        "class",
        "grade",
        "grades",
        "attendance",
        "teacher",
        "teachers",
        "score",
        "scores",
        "subject",
    },
}
MATCH_STOPWORDS = {
    "the",
    "and",
    "with",
    "from",
    "that",
    "this",
    "then",
    "into",
    "for",
    "using",
    "dataset",
    "data",
    "python",
    "script",
    "write",
    "execute",
    "analysis",
    "available",
    "local",
}


def get_dataset_root() -> Path:
    root = Path(settings.dataset_root_dir).resolve()
    root.mkdir(parents=True, exist_ok=True)
    return root


def get_dataset_upload_dir() -> Path:
    upload_dir = Path(settings.dataset_upload_dir).resolve()
    upload_dir.mkdir(parents=True, exist_ok=True)
    return upload_dir


def get_generated_dataset_dir() -> Path:
    generated_dir = get_dataset_root() / "generated"
    generated_dir.mkdir(parents=True, exist_ok=True)
    return generated_dir


def get_generated_dataset_manifest_path() -> Path:
    return get_generated_dataset_dir() / MANIFEST_FILENAME


def discover_local_datasets() -> list[str]:
    datasets: list[str] = []
    root = get_dataset_root()
    manifest_path = get_generated_dataset_manifest_path()
    for path in root.rglob("*"):
        if path.resolve() == manifest_path.resolve():
            continue
        if path.is_file() and path.suffix.lower() in DATASET_EXTENSIONS:
            datasets.append(str(path.resolve()))
    return sorted(datasets)


def _sanitize_filename(filename: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", Path(filename).name).strip("._")
    return cleaned or "dataset.csv"


def _normalize_signature(text: str) -> str:
    return re.sub(r"\s+", " ", text.strip().lower())


def _tokenize_for_matching(text: str) -> set[str]:
    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9]+", text.lower()):
        if len(token) <= 2 or token in MATCH_STOPWORDS:
            continue
        tokens.add(token)
        if token.endswith("s") and len(token) > 4:
            tokens.add(token[:-1])
    return tokens


def infer_dataset_domain(text: str) -> str | None:
    text_lower = text.lower()
    for domain, markers in DATASET_DOMAIN_MARKERS.items():
        if any(marker in text_lower for marker in markers):
            return domain
    return None


def _build_candidate_tokens(
    dataset_path: str,
    summary: str = "",
    columns: list[str] | None = None,
) -> set[str]:
    path = Path(dataset_path)
    candidate_text = " ".join(
        [
            path.stem,
            path.name,
            summary,
            " ".join(columns or []),
        ]
    )
    return _tokenize_for_matching(candidate_text)


def dataset_matches_query(
    query: str,
    dataset_path: str,
    summary: str = "",
    columns: list[str] | None = None,
) -> bool:
    query_tokens = _tokenize_for_matching(query)
    candidate_tokens = _build_candidate_tokens(dataset_path, summary=summary, columns=columns)
    query_domain = infer_dataset_domain(query)
    if query_domain is not None:
        domain_markers = {
            marker for marker in DATASET_DOMAIN_MARKERS[query_domain] if len(marker) > 2
        }
        if candidate_tokens & domain_markers:
            return True
        if "general-purpose" in summary.lower():
            return False

    if query_tokens & candidate_tokens:
        return True
    return False


def choose_dataset_for_query(query: str, dataset_paths: list[str]) -> str | None:
    valid_paths = [str(Path(path).resolve()) for path in dataset_paths if Path(path).exists()]
    if not valid_paths:
        return None

    query_tokens = _tokenize_for_matching(query)
    best_path: str | None = None
    best_score = 0
    for dataset_path in valid_paths:
        path = Path(dataset_path)
        inspected = inspect_dataset_file(dataset_path)
        candidate_tokens = _build_candidate_tokens(
            dataset_path,
            summary=str(inspected.get("summary", "")),
            columns=list(inspected.get("columns", [])),
        )
        score = len(query_tokens & candidate_tokens)
        query_domain = infer_dataset_domain(query)
        if query_domain is not None:
            domain_markers = {
                marker for marker in DATASET_DOMAIN_MARKERS[query_domain] if len(marker) > 2
            }
            if candidate_tokens & domain_markers:
                score += 5
        if score > best_score:
            best_score = score
            best_path = dataset_path

    if best_score > 0:
        return best_path
    if len(valid_paths) == 1:
        query_lower = query.lower()
        generic_dataset_markers = (
            "available dataset",
            "local dataset",
            "the dataset",
            "this dataset",
        )
        if any(marker in query_lower for marker in generic_dataset_markers):
            return valid_paths[0]
    return None


def _load_generated_dataset_manifest() -> list[dict[str, Any]]:
    manifest_path = get_generated_dataset_manifest_path()
    if not manifest_path.exists():
        return []

    try:
        data = json.loads(manifest_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [entry for entry in data if isinstance(entry, dict)]


def _save_generated_dataset_manifest(entries: list[dict[str, Any]]) -> None:
    manifest_path = get_generated_dataset_manifest_path()
    manifest_path.write_text(json.dumps(entries, indent=2), encoding="utf-8")


def find_generated_dataset(query: str) -> dict[str, Any] | None:
    signature = _normalize_signature(query)
    entries = _load_generated_dataset_manifest()
    cleaned_entries: list[dict[str, Any]] = []
    
    # 1. Try Exact Signature Match
    match: dict[str, Any] | None = None
    for entry in entries:
        path = entry.get("path")
        if not path or not Path(path).exists():
            continue
        cleaned_entries.append(entry)
        if entry.get("signature") == signature and match is None:
            if dataset_matches_query(
                query,
                str(path),
                summary=str(entry.get("summary", "")),
                columns=list(entry.get("columns", [])),
            ):
                match = entry

    # 2. Try Semantic Token Match (Fuzzy)
    if match is None:
        best_score = 0
        for entry in cleaned_entries:
            path = entry.get("path")
            if not path:
                continue
            if dataset_matches_query(
                query,
                str(path),
                summary=str(entry.get("summary", "")),
                columns=list(entry.get("columns", [])),
            ):
                # Calculate a simple overlap score
                query_tokens = _tokenize_for_matching(query)
                candidate_tokens = _build_candidate_tokens(
                    str(path),
                    summary=str(entry.get("summary", "")),
                    columns=list(entry.get("columns", [])),
                )
                score = len(query_tokens & candidate_tokens)
                if score > best_score:
                    best_score = score
                    match = entry

    if cleaned_entries != entries:
        _save_generated_dataset_manifest(cleaned_entries)
    return match


def _title_case_filename(name: str) -> str:
    stem = Path(name).stem
    words = [w.capitalize() for w in re.split(r"[._-]+", stem) if w]
    if not words:
        words = ["Generated", "Dataset"]
    return "_".join(words) + ".csv"


def generate_dataset_filename(query: str) -> str:
    query = str(query or "").lower()
    tokens = [token for token in re.findall(r"[a-z0-9]+", query) if len(token) > 3 and token not in MATCH_STOPWORDS]
    if not tokens:
        return "Generated_Dataset.csv"

    selected = "_".join(tokens[:4])
    selected = _sanitize_filename(selected)
    selected = _title_case_filename(selected)
    return selected


def build_dataset_csv(columns: list[str], rows: list[Any]) -> str:
    buffer = StringIO()
    writer = csv.writer(buffer, lineterminator="\n")
    writer.writerow(columns)
    
    formatted_rows = []
    for row in rows:
        if isinstance(row, dict):
            formatted_rows.append([row.get(col, "") for col in columns])
        else:
            formatted_rows.append(row)
            
    writer.writerows(formatted_rows)
    return buffer.getvalue()


def inspect_dataset_file(dataset_path: str) -> dict[str, Any]:
    path = Path(dataset_path).resolve()
    if not path.exists():
        return {
            "path": str(path),
            "columns": [],
            "row_count": None,
            "summary": "Dataset file does not exist.",
        }

    suffix = path.suffix.lower()
    if suffix == ".csv":
        with path.open("r", encoding="utf-8", newline="") as handle:
            reader = csv.reader(handle)
            try:
                columns = [str(c).strip() for c in next(reader)]
            except StopIteration:
                columns = []
                row_count = 0
            else:
                row_count = sum(1 for _ in reader)
        return {
            "path": str(path),
            "columns": columns,
            "row_count": row_count,
            "summary": f"CSV dataset with {row_count} rows.",
        }

    if suffix == ".json":
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
            if isinstance(data, list) and data and isinstance(data[0], dict):
                columns = list(data[0].keys())
                return {
                    "path": str(path),
                    "columns": columns,
                    "row_count": len(data),
                    "summary": f"JSON dataset with {len(data)} records.",
                }
        except Exception:
            pass
        return {
            "path": str(path),
            "columns": [],
            "row_count": None,
            "summary": "JSON dataset detected.",
        }

    if suffix in {".xlsx", ".xls", ".parquet"}:
        try:
            import pandas as pd
            if suffix == ".parquet":
                df = pd.read_parquet(path)
            else:
                df = pd.read_excel(path)
            return {
                "path": str(path),
                "columns": list(df.columns),
                "row_count": len(df),
                "summary": f"{suffix[1:].upper()} dataset with {len(df)} rows.",
            }
        except ImportError:
            return {
                "path": str(path),
                "columns": [],
                "row_count": None,
                "summary": f"{suffix[1:].upper()} file detected (Pandas not available for deep inspection).",
            }
        except Exception as e:
            return {
                "path": str(path),
                "columns": [],
                "row_count": None,
                "summary": f"{suffix[1:].upper()} file detected but inspection failed: {e}",
            }

    if suffix == ".pdf":
        return {
            "path": str(path),
            "columns": [],
            "row_count": None,
            "summary": "PDF Document - Recommended for RAG tasks.",
        }

    if suffix in {".docx", ".doc"}:
        return {
            "path": str(path),
            "columns": [],
            "row_count": None,
            "summary": "Word Document - Recommended for RAG tasks.",
        }

    return {
        "path": str(path),
        "columns": [],
        "row_count": None,
        "summary": f"Dataset file detected: {path.name}",
    }


def save_generated_dataset(
    filename: str,
    content: str,
    source_query: str,
    summary: str,
    columns: list[str],
    row_count: int,
) -> dict[str, Any]:
    generated_dir = get_generated_dataset_dir()
    base_name = _sanitize_filename(filename)
    if Path(base_name).suffix.lower() != ".csv":
        base_name = f"{Path(base_name).stem}.csv"

    signature = _normalize_signature(source_query)
    existing = find_generated_dataset(source_query)
    if existing is not None:
        return existing

    target = generated_dir / base_name
    counter = 1
    while target.exists():
        target = generated_dir / f"{Path(base_name).stem}_{counter}.csv"
        counter += 1

    target.write_text(content, encoding="utf-8")
    entry = {
        "signature": signature,
        "path": str(target.resolve()),
        "source_query": source_query,
        "summary": summary,
        "columns": columns,
        "row_count": row_count,
    }
    manifest = _load_generated_dataset_manifest()
    manifest.append(entry)
    _save_generated_dataset_manifest(manifest)
    return entry


def save_uploaded_dataset(filename: str, content: bytes) -> str:
    upload_dir = get_dataset_upload_dir()
    base_name = _sanitize_filename(filename)
    target = upload_dir / base_name

    if target.exists() and target.read_bytes() == content:
        return str(target.resolve())

    counter = 1
    while target.exists():
        target = upload_dir / f"{Path(base_name).stem}_{counter}{Path(base_name).suffix}"
        counter += 1

    target.write_bytes(content)
    return str(target.resolve())


def prepare_dataset_for_code_exec(dataset_path: str) -> str:
    source = Path(dataset_path).resolve()
    if not source.exists():
        raise FileNotFoundError(f"Dataset not found: {source}")

    dataset_dir = get_sandbox_workspace() / "datasets"
    dataset_dir.mkdir(parents=True, exist_ok=True)
    target_name = _sanitize_filename(source.name)
    target = dataset_dir / target_name

    if not target.exists() or source.read_bytes() != target.read_bytes():
        shutil.copy2(source, target)

    return str(target.resolve())
