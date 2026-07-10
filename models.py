from pydantic import BaseModel
from typing import Optional, List


class NormalizedFailure(BaseModel):
    tool: str
    job_name: str
    error_message: str
    log_excerpt: str
    timestamp: str
    run_id: Optional[str] = None
    environment: str = "production"


# Output of Agent 1 (Log Collector) — extends NormalizedFailure with LLM enrichment
class CollectedFailure(NormalizedFailure):
    severity_hint: Optional[str] = None        # Critical | High | Medium | Low
    error_category: Optional[str] = None       # Authentication failure, Schema mismatch, etc.
    affected_component: Optional[str] = None
    summary: Optional[str] = None              # 1-2 sentence pre-summary from log collector
    relevant_logs: List[str] = []              # filtered log lines, noise removed
    ready_for_analysis: bool = True


# Output of Agent 2 (Diagnosis) — carries CollectedFailure forward + adds root cause
class DiagnosisResult(CollectedFailure):
    root_cause: str
    suggested_fix: str
    severity: str       # "low" | "medium" | "high"
    confidence: str     # "low" | "medium" | "high"


class OwnerInfo(BaseModel):
    name: str
    slack_handle: str
    team: Optional[str] = None