from __future__ import annotations

import chromadb
from langchain_chroma import Chroma

from app.core.config import settings
from app.graph.llm import get_embeddings


def get_vectorstore() -> Chroma:
    client = chromadb.PersistentClient(path=settings.chroma_persist_dir)
    return Chroma(
        client=client,
        collection_name=settings.chroma_collection,
        embedding_function=get_embeddings(),
    )


def retrieve_documents(query: str) -> list[dict[str, object]]:
    """Retrieve relevant documents from the ChromaDB vector store."""
    if not query.strip():
        return []

    try:
        vectorstore = get_vectorstore()
        docs = vectorstore.similarity_search_with_score(
            query,
            k=settings.max_rag_results,
        )
        return [
            {
                "content": doc.page_content,
                "source": doc.metadata.get("source", "unknown"),
                "score": float(score),
            }
            for doc, score in docs
        ]
    except Exception as exc:
        return [
            {
                "content": f"RAG unavailable: {exc}",
                "source": "error",
                "score": 0.0,
            }
        ]
