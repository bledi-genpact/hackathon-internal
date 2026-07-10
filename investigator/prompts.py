"""System prompt and prompt-building for the LLM-driven investigator."""

from __future__ import annotations

from .contracts import TriageObject

SYSTEM_PROMPT = """\
You are the Investigator agent in an automated job-failure diagnosis pipeline.
A triage stage has escalated a failed job to you because it could not resolve it
from rules alone. Your job: find the single most likely ROOT CAUSE and a concrete
FIX, backed by evidence you gather with tools.

How to work:
- Start by calling query_past_incidents with the error signature — a known past
  incident is the strongest signal and often resolves the case immediately.
- Then gather corroborating evidence: search_logs for the failing lines, read_code
  when a traceback points at a file:line, get_recent_deploys to catch regressions,
  check_dependency_health when a downstream service looks involved.
- Call at least two DIFFERENT investigation tools before you conclude, unless a
  past-incident match plus the log already make the cause unambiguous.
- Do not guess when you can check. But do not loop forever — once the evidence
  points clearly at one cause, stop.

When you are ready, call submit_diagnosis exactly once. Be honest about
confidence: high (>=0.75) only when evidence directly supports the cause; low
(<0.45) with needs_human=true when you genuinely cannot tell. Prefer a specific,
actionable root cause and fix over a vague one.
"""


def build_initial_user_message(triage: TriageObject) -> str:
    """The first user turn: everything the investigator knows about the failure."""
    md = triage.metadata or {}
    md_lines = "\n".join(f"  {k}: {v}" for k, v in md.items()) or "  (none)"
    return f"""\
A job has failed and been escalated for investigation.

incident_id: {triage.incident_id}
job_id: {triage.job_id}
triage_category_guess: {triage.category.value}
severity: {triage.severity}
error_signature: {triage.error_signature}

why triage escalated:
{triage.escalated_reason or "(not given)"}

error excerpt:
{triage.error_excerpt or "(none)"}

cleaned log:
{triage.cleaned_log or "(none)"}

metadata:
{md_lines}

Investigate and then call submit_diagnosis.
"""