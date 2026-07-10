"""Data contracts for the Investigator agent (Person 3).

These dataclasses are the *seams* between streams. Keep them stable — Person 6
(integration) wires stages by passing these objects (or their ``to_dict()`` JSON)
across boundaries.

    Person 2 (Triage)  --TriageObject-->  Person 3 (Investigator)  --Diagnosis-->  Person 4 (Explainer)

Everything here is plain stdlib so it imports with zero dependencies. Every
object has ``to_dict`` / ``from_dict`` so a stage can hand off JSON over a queue,
an HTTP call, or a file without importing this module.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field, asdict
from enum import Enum
from typing import Any


# ---------------------------------------------------------------------------
# Shared vocabulary
# ---------------------------------------------------------------------------

class Category(str, Enum):
    """Failure categories shared across triage and investigation.

    ``str`` subclass so a Category serializes to a plain string in JSON and
    compares equal to that string — Person 2 can send ``"dependency"`` and it
    still matches ``Category.DEPENDENCY``.
    """

    DEPENDENCY = "dependency"   # a downstream service / DB / external API failed
    CODE = "code"               # a bug in the job's own code (traceback, bad logic)
    CONFIG = "config"           # missing/incorrect env var, secret, or config value
    INFRA = "infra"             # OOM, disk full, node eviction, timeout
    DATA = "data"               # malformed / unexpected input data
    UNKNOWN = "unknown"         # triage could not classify — needs investigation

    @classmethod
    def coerce(cls, value: Any) -> "Category":
        """Best-effort parse of an arbitrary string into a Category."""
        if isinstance(value, cls):
            return value
        try:
            return cls(str(value).strip().lower())
        except ValueError:
            return cls.UNKNOWN


def confidence_label(score: float) -> str:
    """Map a 0..1 confidence score to a human label (used by Person 4's message)."""
    if score >= 0.75:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


# ---------------------------------------------------------------------------
# Input contract: what the Triage agent (Person 2) hands us
# ---------------------------------------------------------------------------

@dataclass
class TriageObject:
    """The escalation packet produced by triage when it can't auto-resolve.

    Person 1 supplies ``cleaned_log`` / ``error_excerpt`` (redacted, budgeted).
    Person 2 supplies the signature, category guess, and escalation reason.
    """

    incident_id: str
    job_id: str
    error_signature: str                       # normalized fingerprint of the error
    category: Category = Category.UNKNOWN       # triage's best guess
    severity: str = "medium"                    # low | medium | high | critical
    error_excerpt: str = ""                     # the key error region (Person 1)
    cleaned_log: str = ""                        # the 100-line cleaned blob (Person 1)
    escalated_reason: str = ""                  # why triage escalated instead of resolving
    metadata: dict[str, Any] = field(default_factory=dict)  # service, commit_sha, ts, ...

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "TriageObject":
        d = dict(d)
        d["category"] = Category.coerce(d.get("category", Category.UNKNOWN))
        known = {f for f in cls.__dataclass_fields__}  # tolerate extra keys
        return cls(**{k: v for k, v in d.items() if k in known})


# ---------------------------------------------------------------------------
# Output contract: what we hand the Explainer (Person 4)
# ---------------------------------------------------------------------------

@dataclass
class Evidence:
    """One piece of support for the diagnosis, traceable to the tool that found it."""

    source: str          # tool name that produced this, e.g. "query_past_incidents"
    detail: str          # human-readable finding
    snippet: str = ""    # optional raw excerpt (log line, code, status payload)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Evidence":
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})


@dataclass
class Diagnosis:
    """The Investigator's verdict. This is the deliverable Person 4 formats."""

    incident_id: str
    root_cause: str
    category: Category
    confidence: float                                # 0.0 .. 1.0
    summary: str = ""                                # one-liner for the message header
    recommended_fix: str = ""
    suggested_owner: str | None = None
    evidence: list[Evidence] = field(default_factory=list)
    related_past_incidents: list[str] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    reasoning_steps: list[str] = field(default_factory=list)   # trace for the demo/audit
    needs_human: bool = False                        # true when confidence is too low to act
    model: str = "deterministic-fallback"            # which engine produced this
    created_at: float = field(default_factory=time.time)

    @property
    def confidence_label(self) -> str:
        return confidence_label(self.confidence)

    def to_dict(self) -> dict[str, Any]:
        d = asdict(self)
        d["category"] = self.category.value
        d["confidence_label"] = self.confidence_label
        return d

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "Diagnosis":
        d = dict(d)
        d.pop("confidence_label", None)  # derived, not a field
        d["category"] = Category.coerce(d.get("category", Category.UNKNOWN))
        d["evidence"] = [Evidence.from_dict(e) for e in d.get("evidence", [])]
        known = {f for f in cls.__dataclass_fields__}
        return cls(**{k: v for k, v in d.items() if k in known})