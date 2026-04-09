"""Quality Gate — LLM-powered output evaluation for agent responses.

Scores LLM output on Relevance, Depth, Accuracy, and Completeness (1-5 each).
Returns a verdict with actionable feedback for retry prompts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import JsonOutputParser

from app.graph.llm import get_llm
from app.core.config import settings


@dataclass
class QualityVerdict:
    """Result of a quality evaluation."""
    passed: bool
    score: float
    feedback: str
    criteria_scores: dict[str, float] = field(default_factory=dict)
    attempt: int = 1


EVALUATOR_PROMPT = ChatPromptTemplate.from_messages(
    [
        (
            "system",
            """You are a strict quality evaluator for research outputs. Score the given output on these 4 criteria (1-5 each):

1. **Relevance**: Does the output directly address the original query? Does it ONLY include information the user asked for? If the output includes dataset analysis, code results, or charts that the user never requested, score relevance LOW (1-2). (1=off-topic or includes unrequested content, 5=laser-focused on what was asked)
2. **Depth**: Is the analysis thorough with specific details, data points, statistics? (1=surface-level, 5=comprehensive)
3. **Accuracy**: Does it cite evidence and avoid fabrication? Are the data sources actually relevant to the query? (1=speculative or uses irrelevant data, 5=well-sourced with relevant evidence)
4. **Completeness**: Does it cover all aspects of the query? (1=major gaps, 5=exhaustive)

CRITICAL RULES:
- If the user asked a conceptual/research question (e.g. "What are the trends in X?") but the output contains local dataset analysis, synthetic data charts, or code output that the user NEVER requested, the Relevance score MUST be 1-2.
- A report that pads itself with irrelevant analysis to look thorough should score LOW on both Relevance and Accuracy.
- Be strict. A generic or shallow response should score 2-3, not 4-5.

Return ONLY valid JSON with this structure:
{{"relevance": N, "depth": N, "accuracy": N, "completeness": N, "feedback": "Specific, actionable critique of what needs improvement"}}

If the output is solid, set feedback to "No issues detected." """,
        ),
        (
            "human",
            "Original query: {query}\n\nContext type: {context_type}\n\nOutput to evaluate:\n{output}",
        ),
    ]
)


def evaluate_quality(
    query: str,
    output: str,
    context_type: str = "research_report",
    attempt: int = 1,
) -> QualityVerdict:
    """Evaluate LLM output quality against the original query.

    Args:
        query: The original user research query.
        output: The LLM-generated text to evaluate.
        context_type: What kind of output this is (e.g. "summary", "research_report").
        attempt: Which attempt number this evaluation is for.

    Returns:
        QualityVerdict with pass/fail, score, and actionable feedback.
    """
    if not settings.quality_gate_enabled:
        return QualityVerdict(
            passed=True,
            score=5.0,
            feedback="Quality gate disabled.",
            attempt=attempt,
        )

    try:
        llm = get_llm()
        # Truncate output to avoid blowing token limits on the evaluator
        truncated_output = output[:4000] if len(output) > 4000 else output

        response = llm.invoke(
            EVALUATOR_PROMPT.format_messages(
                query=query,
                context_type=context_type,
                output=truncated_output,
            )
        )

        result = JsonOutputParser().parse(str(response.content))

        if not isinstance(result, dict):
            # Unparseable — assume OK to avoid blocking
            return QualityVerdict(
                passed=True,
                score=3.5,
                feedback="Evaluator returned non-dict; defaulting to pass.",
                attempt=attempt,
            )

        criteria = {
            "relevance": float(result.get("relevance", 3)),
            "depth": float(result.get("depth", 3)),
            "accuracy": float(result.get("accuracy", 3)),
            "completeness": float(result.get("completeness", 3)),
        }

        avg_score = sum(criteria.values()) / len(criteria)
        feedback = str(result.get("feedback", "No feedback provided."))

        # Hard floor: if ANY criterion is critically low (≤ 2), fail regardless of average
        has_critical_failure = any(v <= 2.0 for v in criteria.values())
        passed = avg_score >= settings.quality_gate_min_score and not has_critical_failure

        if has_critical_failure and not feedback.startswith("CRITICAL"):
            failed_criteria = [k for k, v in criteria.items() if v <= 2.0]
            feedback = f"CRITICAL: {', '.join(failed_criteria)} scored critically low. {feedback}"

        return QualityVerdict(
            passed=passed,
            score=round(avg_score, 2),
            feedback=feedback,
            criteria_scores=criteria,
            attempt=attempt,
        )

    except Exception as exc:
        # On evaluator failure, don't block the pipeline — pass through
        return QualityVerdict(
            passed=True,
            score=0.0,
            feedback=f"Quality evaluation failed: {exc}. Passing through.",
            attempt=attempt,
        )
