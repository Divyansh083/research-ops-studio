from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.graph.llm import get_llm
from app.graph.state import ResearchState

SUMMARISER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior research summariser. Given the original query and gathered evidence,
produce a highly detailed and comprehensive summary of all relevant facts, data points, and context.
Do not omit important nuances or statistics. Include inline citations as [Source: url_or_doc]
where available. Be factual, analytical, and directly relevant to the query.""",
        ),
        ("human", "Query: {query}\n\nEvidence:\n{evidence}"),
    ]
)


def _build_evidence_text(state: ResearchState) -> str:
    evidence_chunks: list[str] = []

    for dataset in state.get("dataset_outputs", [])[:4]:
        evidence_chunks.append(
            f"- Dataset [{dataset.get('status', 'unknown')}]: {dataset.get('path', 'N/A')}\n"
            f"  Summary: {dataset.get('summary', '')}\n"
            f"  Rows: {dataset.get('row_count', 'N/A')}\n"
            f"  Columns: {', '.join(dataset.get('columns', [])) or 'N/A'}\n"
            f"  Note: {dataset.get('note', 'N/A')}"
        )

    for result in state.get("search_results", [])[:8]:
        evidence_chunks.append(
            f"- Search: {result.get('title', 'Source')}\n"
            f"  Snippet: {result.get('snippet', '')[:400]}\n"
            f"  URL: {result.get('url', 'N/A')}"
        )

    for result in state.get("rag_results", [])[:8]:
        evidence_chunks.append(
            f"- RAG: {result.get('source', 'Document')}\n"
            f"  Content: {result.get('content', '')[:400]}\n"
            f"  Score: {result.get('score', 'N/A')}"
        )

    for output in state.get("code_outputs", [])[:4]:
        if output.get("error"):
            evidence_chunks.append(f"- Code error: {output.get('error')}")
        else:
            evidence_chunks.append(
                f"- Code output:\n"
                f"  Code: {output.get('code', '')[:300]}\n"
                f"  Output: {output.get('output', '')[:400]}"
            )

    return "\n\n".join(evidence_chunks)


def summariser_node(state: ResearchState) -> dict:
    query = state["query"]
    evidence_text = _build_evidence_text(state)
    if not evidence_text.strip():
        return {
            "summaries": [f"No results found for: {query}"],
            "agent_log": [f"Summariser: no results to summarise for '{query}'"],
        }

    try:
        llm = get_llm()
        response = llm.invoke(
            SUMMARISER_PROMPT.format_messages(query=query, evidence=evidence_text)
        )
        return {
            "summaries": [str(response.content)],
            "agent_log": [f"Summariser agent completed for '{query}'"],
        }
    except Exception as exc:
        return {
            "summaries": [f"Summary failed: {exc}"],
            "error_log": [f"Summariser error: {exc}"],
            "agent_log": [f"Summariser agent failed for '{query}'"],
        }
