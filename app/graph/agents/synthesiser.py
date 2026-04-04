from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.graph.llm import get_llm
from app.graph.state import ResearchState

SYNTHESISER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior, highly analytical research expert. Synthesise the findings below into an extremely comprehensive, in-depth, and highly detailed report in Markdown.
Do NOT just summarize briefly. Expand aggressively on the implications of the data. Write multi-paragraph analyses and detailed bullet points for every piece of information.

Use this structure exactly, ensuring each section is content-rich and highly detailed:
## Executive Summary
(Write a full, dense paragraph overviewing the entire dataset and purpose)
## Key Findings
(List out every notable metric, fact, or statistic with extensive context)
## Analysis
(Provide a deep, multi-paragraph breakdown of what the data means, trends, and significance)
## Code Output and Data
(Detail the mathematical and programmatic results returned by the code agent)
## Sources
(List all URLs and references)

Be extremely factual, analytical, and cite sources throughout.
Only describe code-derived findings when there are successful execution outputs.
If code was generated but skipped or failed, say that clearly and do not infer hypothetical charts.
If the code output mentions generated artifacts, list them clearly as visual or data evidence and explain what they represent.""",
        ),
        (
            "human",
            """Original query: {query}

Summaries from agents:
{summaries}

Dataset preparation outputs:
{dataset_outputs}

Raw search results:
{search_results}

Code execution outputs:
{code_outputs}

Generated code attempts:
{code_attempts}

Additional RAG context:
{rag_results}

Non-fatal errors:
{errors}
""",
        ),
    ]
)

FALLBACK_SYNTHESISER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior research analyst. No retrieved evidence is available, but the
user still needs a helpful answer. Answer the query using general model knowledge.

Rules:
- Do not invent citations or external sources.
- Be explicit that the answer is an uncited best-effort response.
- If tool errors are available, mention them briefly in a Limitations section.

Use this structure:
## Executive Summary
## Key Findings
## Analysis
## Limitations
## Sources""",
        ),
        (
            "human",
            "Original query: {query}\n\nTool errors:\n{errors}",
        ),
    ]
)


def _has_evidence(state: ResearchState) -> bool:
    if state.get("dataset_outputs"):
        return True
    if state.get("search_results"):
        return True
    if state.get("rag_results"):
        return True
    return any(not item.get("error") for item in state.get("code_outputs", []))


def synthesiser_node(state: ResearchState) -> dict:
    try:
        summaries_text = "\n\n".join(state.get("summaries", [])) or "No summaries available."
        search_text = "\n".join(
            [
                f"- [{result.get('title', 'Source')}]({result.get('url', '#')}): "
                f"{result.get('snippet', '')[:300]}"
                for result in state.get("search_results", [])
            ]
        ) or "No web results."
        rag_text = "\n".join(
            [
                f"- {result.get('source', 'Document')}: {result.get('content', '')[:300]}"
                for result in state.get("rag_results", [])
            ]
        ) or "No RAG results."
        dataset_text = "\n".join(
            [
                (
                    f"- Dataset [{item.get('status', 'unknown')}]: {item.get('path', 'N/A')}\n"
                    f"  Summary: {item.get('summary', '')}\n"
                    f"  Rows: {item.get('row_count', 'N/A')}\n"
                    f"  Columns: {', '.join(item.get('columns', [])) or 'N/A'}\n"
                    f"  Note: {item.get('note', 'N/A')}"
                )
                for item in state.get("dataset_outputs", [])
            ]
        ) or "No dataset preparation outputs."
        code_text = "\n".join(
            [
                (
                    f"Dataset source: {item.get('dataset_source_path', 'N/A')}\n"
                    f"Dataset used in sandbox: {item.get('dataset_path', 'N/A')}\n"
                    f"```python\n{item.get('code', '')}\n```\n"
                    f"Output: {item.get('output', '')}\n"
                    f"Generated Artifacts: {', '.join(item.get('artifacts', [])) or 'None'}"
                )
                for item in state.get("code_outputs", [])
                if item.get("status") == "success"
            ]
        ) or "No code execution outputs."
        code_attempts_text = "\n\n".join(
            [
                f"Status: {item.get('status', 'unknown')}\n"
                f"Dataset source: {item.get('dataset_source_path', 'N/A')}\n"
                f"Dataset used in sandbox: {item.get('dataset_path', 'N/A')}\n"
                f"Note: {item.get('note', item.get('error', ''))}\n"
                f"```python\n{item.get('code', '')}\n```"
                for item in state.get("code_outputs", [])
                if item.get("code")
            ]
        ) or "No generated code attempts."

        # Filter out errors from the error_log if they are just transient CodeExec/sandbox
        # errors that were successfully recovered from on retry.
        active_errors = []
        has_successful_code = any(item.get("status") == "success" for item in state.get("code_outputs", []))
        
        for err in state.get("error_log", []):
            is_transient_exec_error = err.startswith("CodeExec agent runtime error") or err.startswith("Sandbox auto-setup failed")
            if is_transient_exec_error and has_successful_code:
                continue
            active_errors.append(err)

        llm = get_llm()
        if _has_evidence(state):
            response = llm.invoke(
                SYNTHESISER_PROMPT.format_messages(
                    query=state["query"],
                    summaries=summaries_text,
                    dataset_outputs=dataset_text,
                    search_results=search_text,
                    rag_results=rag_text,
                    code_outputs=code_text,
                    code_attempts=code_attempts_text,
                    errors="\n".join(active_errors) or "No non-fatal errors.",
                )
            )
            report_text = str(response.content)
            agent_message = "Synthesiser: final report generated successfully"
        else:
            response = llm.invoke(
                FALLBACK_SYNTHESISER_PROMPT.format_messages(
                    query=state["query"],
                    errors="\n".join(state.get("error_log", [])) or "No tool errors logged.",
                )
            )
            report_text = str(response.content)
            agent_message = "Synthesiser: fallback report generated from model knowledge"

        return {
            "final_report": report_text,
            "agent_log": [agent_message],
        }
    except Exception as exc:
        fallback_report = (
            "# Report Generation Failed\n\n"
            f"Error: {exc}\n\n"
            "Raw summaries:\n\n"
            + "\n\n".join(state.get("summaries", []))
        )
        return {
            "final_report": fallback_report,
            "error_log": [f"Synthesiser error: {exc}"],
            "agent_log": ["Synthesiser: failed, returned raw summaries as fallback"],
        }
