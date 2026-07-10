"""Confidence scoring.

Two independent signals, deliberately kept separate so the demo can explain the
number:

  * The LLM's *self-reported* confidence in ``submit_diagnosis`` (its own belief).
  * A *heuristic* score derived only from the evidence actually gathered — how
    many distinct tools returned something, whether a past incident matched,
    whether the offending code/deploy was pinpointed, whether the category was
    resolved.

We blend them so a model that is over-confident with thin evidence gets pulled
down, and a model that under-rates strong evidence gets pulled up. The
deterministic fallback (no LLM) uses the heuristic alone.
"""

from __future__ import annotations

from .contracts import Category, Evidence


def heuristic_score(
    *,
    category: Category,
    tools_used: list[str],
    evidence: list[Evidence],
    matched_past_incident: bool,
    pinpointed_location: bool,
) -> float:
    """Evidence-only confidence in 0.05..0.98."""
    score = 0.15  

    distinct_investigation_tools = {
        t for t in tools_used if t != "submit_diagnosis"
    }
    .
    score += min(len(distinct_investigation_tools), 3) * 0.12

   
    if evidence:
        score += 0.08

    
    if matched_past_incident:
        score += 0.30

   
    if pinpointed_location:
        score += 0.18

   
    if category == Category.UNKNOWN:
        score = min(score, 0.40)

    return max(0.05, min(score, 0.98))


def blend(model_confidence: float, heuristic: float) -> float:
    """Combine the model's self-report with the evidence heuristic.

    Weighted toward the heuristic (evidence over vibes), but the model's read
    still moves the number. Clamped to 0.05..0.98.
    """
    blended = 0.4 * model_confidence + 0.6 * heuristic
    return max(0.05, min(blended, 0.98))