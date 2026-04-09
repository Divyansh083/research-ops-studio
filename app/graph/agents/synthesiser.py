from __future__ import annotations

from langchain_core.prompts import ChatPromptTemplate

from app.graph.llm import get_llm
from app.graph.state import ResearchState
from app.graph.quality_loop import quality_loop

SYNTHESISER_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a senior, highly analytical research expert. Synthesise the findings below into a report in Markdown.

ADAPTIVE LENGTH RULE:
- If the query is a simple factual question (e.g. "what is today's date", "who founded X", "what is the capital of Y"), give a SHORT, direct answer in 2-5 sentences. Do NOT create multiple sections or pad with generic advice.
- If the query is a complex research question, produce a comprehensive, in-depth, and highly detailed report using the full structure below.

For COMPLEX queries, use this structure exactly, ensuring each section is content-rich:
## Executive Summary
(Write a full, dense paragraph overviewing the entire dataset and purpose)
## Key Findings
(List out every notable metric, fact, or statistic with extensive context)
## Analysis
(Provide a deep, multi-paragraph breakdown of what the data means, trends, and significance)
## Code Output and Data
(Detail the mathematical and programmatic results returned by the code agent — ONLY if code was executed)
## Sources
(List all URLs and references)

Be extremely factual, analytical, and cite sources throughout.
Only describe code-derived findings when there are successful execution outputs.
If code was generated but skipped or failed, say that clearly and do not infer hypothetical charts.
If the code output mentions generated artifacts, list them clearly as visual or data evidence and explain what they represent.
NEVER include generic "best practices", "recommendations", or "tips" sections unless the user explicitly asked for advice.""",
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

        # Filter out transient errors
        active_errors = []
        has_successful_code = any(item.get("status") == "success" for item in state.get("code_outputs", []))
        
        for err in state.get("error_log", []):
            is_transient_exec_error = err.startswith("CodeExec agent runtime error") or err.startswith("Sandbox auto-setup failed")
            if is_transient_exec_error and has_successful_code:
                continue
            active_errors.append(err)

        llm = get_llm()
        query = state["query"]
        has_evidence = _has_evidence(state)

        # === Quality-gated generation ===
        def _generate() -> str:
            if has_evidence:
                response = llm.invoke(
                    SYNTHESISER_PROMPT.format_messages(
                        query=query,
                        summaries=summaries_text,
                        dataset_outputs=dataset_text,
                        search_results=search_text,
                        rag_results=rag_text,
                        code_outputs=code_text,
                        code_attempts=code_attempts_text,
                        errors="\n".join(active_errors) or "No non-fatal errors.",
                    )
                )
            else:
                response = llm.invoke(
                    FALLBACK_SYNTHESISER_PROMPT.format_messages(
                        query=query,
                        errors="\n".join(state.get("error_log", [])) or "No tool errors logged.",
                    )
                )
            return str(response.content)

        loop_result = quality_loop(
            generate_fn=_generate,
            query=query,
            context_type="research_report",
        )

        # Build agent log with quality metadata
        agent_logs = []
        for verdict in loop_result.history:
            scores = verdict.criteria_scores
            score_detail = ", ".join(f"{k}={v}" for k, v in scores.items()) if scores else "n/a"
            status = "accepted" if verdict.passed else "retrying"
            agent_logs.append(
                f"Synthesiser attempt {verdict.attempt}: quality {verdict.score}/5 "
                f"({score_detail}) — {status}"
            )

        if has_evidence:
            agent_logs.append("Synthesiser: final report generated successfully")
        else:
            agent_logs.append("Synthesiser: fallback report generated from model knowledge")

        return {
            "final_report": loop_result.output,
            "agent_log": agent_logs,
        }
    except Exception as exc:
        err_msg = str(exc)
        
        # Check if it's a 429 Rate Limit Error
        if "429" in err_msg or "rate_limit_exceeded" in err_msg:
            fallback_report = (
                "# ⚠️ Critical System Notice: Rate Limit Exceeded\n\n"
                "> The AI model API (Groq) has reached its token limits. The research run was paused to prevent data loss.\n\n"
                "*Please wait a few minutes before trying the query again, or switch to an alternate model in the configuration.*"
            )
        else:
            fallback_report = (
                "# Report Generation Failed\n\n"
                f"**Error Details:**\n```\n{err_msg}\n```\n\n"
            )
            
        return {
            "final_report": fallback_report,
            "error_log": [f"Synthesiser error: {exc}"],
            "agent_log": ["Synthesiser: failed, returned formatted error block"],
        }
