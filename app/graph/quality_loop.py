"""Quality Loop — Reusable generate → evaluate → retry wrapper.

Wraps any LLM generation function with automatic quality validation.
On failure, feeds evaluator critique back to the LLM for targeted improvement.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable

from langchain_core.prompts import ChatPromptTemplate

from app.graph.llm import get_llm
from app.graph.quality_gate import QualityVerdict, evaluate_quality
from app.core.config import settings


@dataclass
class QualityLoopResult:
    """Final output from a quality-gated generation."""
    output: str
    attempts: int
    final_score: float
    history: list[QualityVerdict] = field(default_factory=list)
    passed: bool = True


REFINEMENT_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are improving a research output that was flagged for low quality.

Your previous attempt scored {score}/5.0 (minimum required: {min_score}).

Quality feedback from evaluator:
{feedback}

Criteria breakdown:
- Relevance: {relevance}/5
- Depth: {depth}/5
- Accuracy: {accuracy}/5
- Completeness: {completeness}/5

CRITICAL RULES FOR REWRITING:
1. RELEVANCE IS KING. If relevance scored low, your output contained information the user did NOT ask for. REMOVE all irrelevant content ruthlessly.
2. If the query is a simple factual question (e.g. "what is today's date", "who is the CEO of X"), give a SHORT direct answer. Do NOT pad with generic advice, technical tutorials, or filler sections.
3. If the query is a complex research question, be thorough and detailed with evidence.
4. NEVER include generic "best practices", "recommendations", or "tips" sections unless the user specifically asked for them.
5. Match the LENGTH of your response to the COMPLEXITY of the query. Simple query = short answer. Complex query = detailed report.
6. Do not repeat the same content from your previous attempt.""",
        ),
        (
            "human",
            "Original query: {query}\n\nPrevious output to improve:\n{previous_output}",
        ),
    ]
)


def quality_loop(
    generate_fn: Callable[[], str],
    query: str,
    context_type: str = "research_report",
    max_retries: int | None = None,
    min_score: float | None = None,
) -> QualityLoopResult:
    """Run a generation function with quality evaluation and automatic retry.

    Args:
        generate_fn: A callable that returns the LLM-generated text string.
        query: The original user query (used for evaluation context).
        context_type: Type of output being evaluated (e.g. "summary", "research_report").
        max_retries: Override the config-level max retries. None = use config.
        min_score: Override the config-level min score. None = use config.

    Returns:
        QualityLoopResult with the best output and evaluation history.
    """
    effective_max_retries = max_retries if max_retries is not None else settings.quality_gate_max_retries
    effective_min_score = min_score if min_score is not None else settings.quality_gate_min_score

    if not settings.quality_gate_enabled:
        output = generate_fn()
        return QualityLoopResult(
            output=output,
            attempts=1,
            final_score=5.0,
            passed=True,
        )

    # === Attempt 1: Initial generation ===
    current_output = generate_fn()
    history: list[QualityVerdict] = []

    for attempt in range(1, effective_max_retries + 2):  # +2 because attempt 1 is the initial
        verdict = evaluate_quality(
            query=query,
            output=current_output,
            context_type=context_type,
            attempt=attempt,
        )
        history.append(verdict)

        if verdict.passed:
            return QualityLoopResult(
                output=current_output,
                attempts=attempt,
                final_score=verdict.score,
                history=history,
                passed=True,
            )

        # Max retries exhausted — return what we have
        if attempt > effective_max_retries:
            break

        # === Retry: Feed critique back to LLM ===
        try:
            llm = get_llm()
            criteria = verdict.criteria_scores
            refinement_response = llm.invoke(
                REFINEMENT_PROMPT.format_messages(
                    score=verdict.score,
                    min_score=effective_min_score,
                    feedback=verdict.feedback,
                    relevance=criteria.get("relevance", "?"),
                    depth=criteria.get("depth", "?"),
                    accuracy=criteria.get("accuracy", "?"),
                    completeness=criteria.get("completeness", "?"),
                    query=query,
                    previous_output=current_output[:3000],  # Truncate for token safety
                )
            )
            current_output = str(refinement_response.content)
        except Exception:
            # If refinement itself fails, stop retrying
            break

    # Return the best attempt even if it didn't pass
    return QualityLoopResult(
        output=current_output,
        attempts=len(history),
        final_score=history[-1].score if history else 0.0,
        history=history,
        passed=False,
    )
