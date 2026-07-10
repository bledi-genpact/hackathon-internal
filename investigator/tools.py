"""The Investigator's tools.

A ``Tool`` bundles three things:
  * ``name`` / ``description`` / ``input_schema`` — the JSON contract the LLM sees
    (this is exactly the shape the Anthropic Messages API expects in ``tools=[...]``).
  * ``run(**kwargs)`` — the Python implementation the reasoning loop actually calls.

The implementations here are MOCKS backed by ``mock_data`` so the whole system
runs offline for the demo. To go live, replace a ``run`` function with one that
hits the real store (Person 1's logs, Person 5's SQLite, a real status page) —
keep the return shape and neither the LLM loop nor the deterministic fallback
needs to change.

Every tool returns a JSON-serializable ``dict``. On a miss it returns
``{"found": False, ...}`` rather than raising, so the reasoning loop can feed the
result straight back to the model (or a rule) without special-casing exceptions.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable

from . import mock_data


@dataclass
class Tool:
    name: str
    description: str
    input_schema: dict[str, Any]
    run: Callable[..., dict[str, Any]]

    def to_anthropic_schema(self) -> dict[str, Any]:
        """The dict shape for the Messages API ``tools`` parameter."""
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": self.input_schema,
        }


# ---------------------------------------------------------------------------
# Mock implementations
# ---------------------------------------------------------------------------

def _search_logs(pattern: str, job_id: str = "", **_: Any) -> dict[str, Any]:
    """Grep the (cleaned) log for lines containing ``pattern``."""
    log = mock_data.FULL_LOGS.get(job_id, "")
    if not log:
        # Fall back to scanning every known log if the job wasn't specified.
        log = "\n".join(mock_data.FULL_LOGS.values())
    needle = pattern.lower()
    matches = [ln for ln in log.splitlines() if needle in ln.lower()]
    return {"found": bool(matches), "pattern": pattern,
            "match_count": len(matches), "matches": matches[:20]}


def _read_code(file: str, line: int = 0, context: int = 3, **_: Any) -> dict[str, Any]:
    """Return the source around ``file:line`` (mock: keyed exact matches)."""
    key = f"{file}:{line}"
    snippet = mock_data.SOURCE_SNIPPETS.get(key)
    if snippet is None:
        # try any snippet for the file regardless of line
        for k, v in mock_data.SOURCE_SNIPPETS.items():
            if k.startswith(f"{file}:"):
                snippet = v
                break
    if snippet is None:
        return {"found": False, "file": file, "line": line,
                "detail": "no source available for that location"}
    return {"found": True, "file": file, "line": line, "snippet": snippet}


def _get_recent_deploys(service: str, limit: int = 5, **_: Any) -> dict[str, Any]:
    """Recent deploys/commits for a service, newest first."""
    deploys = mock_data.DEPLOY_HISTORY.get(service, [])
    return {"found": bool(deploys), "service": service,
            "deploys": deploys[:limit]}


def _check_dependency_health(service: str, **_: Any) -> dict[str, Any]:
    """Current health of a downstream dependency (DB, external API, ...)."""
    health = mock_data.SERVICE_HEALTH.get(service)
    if health is None:
        return {"found": False, "service": service,
                "detail": "no health data for that dependency"}
    return {"found": True, "service": service, **health}


def _query_past_incidents(error_signature: str, **_: Any) -> dict[str, Any]:
    """Look up similar past failures + their fixes (Person 5's memory store).

    Mock matches when the stored ``signature_contains`` substring appears in the
    query signature. Real impl: a LIKE / embedding query against SQLite.
    """
    sig = error_signature.lower()
    hits = [inc for inc in mock_data.PAST_INCIDENTS
            if inc["signature_contains"].lower() in sig]
    return {"found": bool(hits), "match_count": len(hits),
            "incidents": [
                {k: v for k, v in inc.items() if k != "signature_contains"}
                for inc in hits
            ]}


# ---------------------------------------------------------------------------
# The special "stop" tool. The model calls this exactly once when it is ready to
# commit to a verdict — it is the primary stop condition for the LLM loop.
# ---------------------------------------------------------------------------

def _submit_diagnosis(**kwargs: Any) -> dict[str, Any]:
    """Record the final diagnosis. Handled specially by the reasoning loop."""
    return {"accepted": True, "diagnosis": kwargs}


SUBMIT_DIAGNOSIS_TOOL = Tool(
    name="submit_diagnosis",
    description=(
        "Call this ONCE when you have gathered enough evidence to commit to a "
        "root cause. This ends the investigation. Provide your best root cause, "
        "a concrete recommended fix, the category, and an honest confidence "
        "(0.0-1.0) reflecting how sure you are. If you cannot determine the root "
        "cause, submit with low confidence and needs_human=true."
    ),
    input_schema={
        "type": "object",
        "properties": {
            "root_cause": {"type": "string",
                           "description": "The single most likely root cause, specific and actionable."},
            "category": {"type": "string",
                         "enum": ["dependency", "code", "config", "infra", "data", "unknown"]},
            "recommended_fix": {"type": "string",
                                "description": "Concrete next step to resolve or mitigate."},
            "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0,
                           "description": "How sure you are, 0.0-1.0."},
            "summary": {"type": "string", "description": "One-sentence headline."},
            "suggested_owner": {"type": "string",
                                "description": "Team/owner best placed to fix it, if known."},
            "needs_human": {"type": "boolean",
                            "description": "True if confidence is too low to act automatically."},
        },
        "required": ["root_cause", "category", "recommended_fix", "confidence"],
        "additionalProperties": False,
    },
    run=_submit_diagnosis,
)


# ---------------------------------------------------------------------------
# Investigation tool registry (everything except the stop tool)
# ---------------------------------------------------------------------------

INVESTIGATION_TOOLS: list[Tool] = [
    Tool(
        name="query_past_incidents",
        description=(
            "Search the memory store of past failures for incidents with a similar "
            "error signature and return their recorded root cause and fix. ALWAYS "
            "worth trying first — a match is the strongest single signal."
        ),
        input_schema={
            "type": "object",
            "properties": {
                "error_signature": {"type": "string",
                                    "description": "The normalized error signature to match on."},
            },
            "required": ["error_signature"],
            "additionalProperties": False,
        },
        run=_query_past_incidents,
    ),
    Tool(
        name="search_logs",
        description="Grep the job's cleaned log for lines matching a pattern (substring, case-insensitive).",
        input_schema={
            "type": "object",
            "properties": {
                "pattern": {"type": "string", "description": "Substring to search for."},
                "job_id": {"type": "string", "description": "Job whose log to search."},
            },
            "required": ["pattern"],
            "additionalProperties": False,
        },
        run=_search_logs,
    ),
    Tool(
        name="read_code",
        description="Read the source lines around a file:line location referenced by a traceback.",
        input_schema={
            "type": "object",
            "properties": {
                "file": {"type": "string", "description": "Source file path."},
                "line": {"type": "integer", "description": "Line number from the traceback."},
                "context": {"type": "integer", "description": "Lines of context each side."},
            },
            "required": ["file", "line"],
            "additionalProperties": False,
        },
        run=_read_code,
    ),
    Tool(
        name="get_recent_deploys",
        description="List recent deploys/commits for a service, newest first, to spot regressions.",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string", "description": "Service name."},
                "limit": {"type": "integer", "description": "Max deploys to return."},
            },
            "required": ["service"],
            "additionalProperties": False,
        },
        run=_get_recent_deploys,
    ),
    Tool(
        name="check_dependency_health",
        description="Check the current health/status of a downstream dependency (DB, external API).",
        input_schema={
            "type": "object",
            "properties": {
                "service": {"type": "string",
                            "description": "Dependency name, e.g. 'orders-db'."},
            },
            "required": ["service"],
            "additionalProperties": False,
        },
        run=_check_dependency_health,
    ),
]


def all_tools() -> list[Tool]:
    """Investigation tools plus the submit-diagnosis stop tool."""
    return [*INVESTIGATION_TOOLS, SUBMIT_DIAGNOSIS_TOOL]


def registry() -> dict[str, Tool]:
    """Name -> Tool lookup, used by the reasoning loop to dispatch calls."""
    return {t.name: t for t in all_tools()}


def execute(name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
    """Dispatch a tool call by name. Never raises for a bad call — returns an
    error dict so the reasoning loop can hand it back to the model."""
    tool = registry().get(name)
    if tool is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return tool.run(**tool_input)
    except Exception as exc:  # keep the loop alive; surface the error as data
        return {"error": f"{type(exc).__name__}: {exc}"}


def as_json(result: dict[str, Any]) -> str:
    """Serialize a tool result for the model's tool_result content block."""
    return json.dumps(result, ensure_ascii=False, indent=2)