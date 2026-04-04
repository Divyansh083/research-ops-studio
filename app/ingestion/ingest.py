"""
CLI usage:
    python -m app.ingestion.ingest --path ./data/sample_docs
    python -m app.ingestion.ingest --path ./data/sample_docs --reset
"""

from __future__ import annotations

import argparse
from pathlib import Path

import chromadb
from langchain_chroma import Chroma
from langchain_community.document_loaders import PyPDFLoader, TextLoader, UnstructuredWordDocumentLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from app.core.config import settings
from app.graph.llm import get_embeddings


def ingest_documents(docs_path: str, reset: bool = False) -> int:
    path = Path(docs_path)
    if not path.exists():
        raise FileNotFoundError(f"Path {docs_path} does not exist")

    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)

    if reset:
        try:
            client.delete_collection(settings.chroma_collection)
            print(f"Deleted existing collection: {settings.chroma_collection}")
        except Exception:
            pass

    loader_specs: list[tuple[Path, object]] = []
    for file_path in sorted(path.rglob("*.pdf")):
        loader_specs.append((file_path, PyPDFLoader(str(file_path))))
    for file_path in sorted(path.rglob("*.txt")):
        loader_specs.append((file_path, TextLoader(str(file_path), encoding="utf-8")))
    for file_path in sorted(path.rglob("*.docx")):
        loader_specs.append((file_path, UnstructuredWordDocumentLoader(str(file_path))))
    for file_path in sorted(path.rglob("*.doc")):
        loader_specs.append((file_path, UnstructuredWordDocumentLoader(str(file_path))))

    if not loader_specs:
        print(f"No PDF, Word (.docx/.doc), or .txt files found in {docs_path}")
        return 0

    splitter = RecursiveCharacterTextSplitter(chunk_size=1000, chunk_overlap=200)
    all_docs = []

    for file_path, loader in loader_specs:
        try:
            docs = loader.load()
            chunks = splitter.split_documents(docs)
            for chunk in chunks:
                chunk.metadata["source"] = str(file_path)
            all_docs.extend(chunks)
            print(f"Loaded: {file_path} -> {len(chunks)} chunks")
        except Exception as exc:
            print(f"Error loading {file_path}: {exc}")

    vectorstore = Chroma(
        client=client,
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
    )
    vectorstore.add_documents(all_docs)

    print(
        f"\nIngestion complete: {len(all_docs)} chunks added to "
        f"'{settings.chroma_collection}'"
    )
    return len(all_docs)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--path", default="./data/sample_docs")
    parser.add_argument(
        "--reset",
        action="store_true",
        help="Delete existing collection first",
    )
    args = parser.parse_args()
    ingest_documents(args.path, args.reset)
