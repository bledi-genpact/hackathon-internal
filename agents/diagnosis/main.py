import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
import anthropic
from fastapi import FastAPI, HTTPException
from models import CollectedFailure, DiagnosisResult
from utils import parse_llm_json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Diagnosis Agent")
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_SYSTEM = """You are a senior data engineer performing root cause analysis on a pipeline failure.

The Log Collector agent has already parsed and pre-classified this failure for you.
Your job is to go deeper: explain WHY this happened in plain English that a junior engineer
can understand, and give a concrete, step-by-step fix they can act on immediately.

Respond with ONLY valid JSON — no markdown, no extra text.

Schema:
{
  "root_cause": "2-4 sentences explaining the underlying reason this failure occurred, in plain English",
  "suggested_fix": "numbered step-by-step actions the engineer should take right now to resolve it",
  "severity": "low | medium | high",
  "confidence": "low | medium | high"
}"""


@app.get("/health")
def health():
    return {"status": "ok", "service": "diagnosis", "port": 8002}


@app.post("/diagnose", response_model=DiagnosisResult)
def diagnose(failure: CollectedFailure):
    if not failure.ready_for_analysis:
        raise HTTPException(
            status_code=422,
            detail="Log Collector flagged this failure as not ready for analysis — insufficient log data.",
        )

    relevant = "\n".join(failure.relevant_logs) if failure.relevant_logs else failure.log_excerpt

    prompt = f"""Pipeline failure to diagnose:

Tool:               {failure.tool.upper()}
Job:                {failure.job_name}
Environment:        {failure.environment}
Error category:     {failure.error_category or "Unknown"}
Affected component: {failure.affected_component or "Unknown"}
Severity hint:      {failure.severity_hint or "Unknown"}
Pre-summary:        {failure.summary or "None"}

Original error message:
{failure.error_message}

Relevant log lines (noise already removed by Log Collector):
{relevant}"""

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2048,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    try:
        data = parse_llm_json(response.content[0].text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse Claude response: {exc}")

    return DiagnosisResult(
        **failure.model_dump(),
        root_cause=data["root_cause"],
        suggested_fix=data["suggested_fix"],
        severity=data.get("severity", "medium"),
        confidence=data.get("confidence", "medium"),
    )