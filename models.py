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



class CollectedFailure(NormalizedFailure):
    severity_hint: Optional[str] = None        
    error_category: Optional[str] = None       
    affected_component: Optional[str] = None
    summary: Optional[str] = None             
    relevant_logs: List[str] = []             
    ready_for_analysis: bool = True



class DiagnosisResult(CollectedFailure):
    root_cause: str
    suggested_fix: str
    severity: str       
    confidence: str     


class OwnerInfo(BaseModel):
    name: str
    slack_handle: str
    team: Optional[str] = None