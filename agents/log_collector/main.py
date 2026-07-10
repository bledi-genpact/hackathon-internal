import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
import json
from datetime import datetime
import anthropic
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from models import CollectedFailure
from utils import parse_llm_json
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Log Collector Agent")
_client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

_SYSTEM = """You are a Log Collector Agent in an AI-powered incident diagnosis system.
You are given already-parsed failure info (job name, environment, error message, log excerpt)
for a pipeline run. Enrich it for the next agent by identifying:

- error severity: high | medium | low
- error category: one of Authentication failure, Permission issue, Network/connectivity problem,
  Database failure, Schema mismatch, Configuration issue, Resource limitation, Unknown
- the affected component/service name (e.g. "PROD_DB.RAW.STRIPE_CHARGES", "snowflake_prod connection", "HubSpot API")
- a one-to-two sentence plain-English summary of what failed
- the relevant log lines only — drop INFO lines, repeated lines, and successful steps; keep only lines that show the error
- whether there is enough information for root-cause analysis (ready_for_analysis)

Do not try to fix the problem. Respond with ONLY valid JSON — no markdown, no extra text.

Schema:
{
  "severity_hint": "high | medium | low",
  "error_category": "...",
  "affected_component": "...",
  "summary": "...",
  "relevant_logs": ["...", "..."],
  "ready_for_analysis": true
}"""


class RawEvent(BaseModel):
    tool: str
    raw_payload: dict


@app.get("/health")
def health():
    return {"status": "ok", "service": "log-collector", "port": 8001}


@app.post("/collect", response_model=CollectedFailure)
def collect(event: RawEvent):
    parsers = {"airflow": _airflow, "dbt": _dbt, "fivetran": _fivetran}
    parser = parsers.get(event.tool)
    if not parser:
        raise HTTPException(status_code=400, detail=f"Unsupported tool: {event.tool}")

    fields = parser(event.raw_payload)
    enrichment = _enrich(event.tool, fields)
    return CollectedFailure(tool=event.tool, **fields, **enrichment)


def _enrich(tool: str, fields: dict) -> dict:
    prompt = f"""Tool: {tool}
Job: {fields['job_name']}
Environment: {fields['environment']}
Error: {fields['error_message']}

Log excerpt:
{fields['log_excerpt']}"""

    try:
        response = _client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=1024,
            system=_SYSTEM,
            messages=[{"role": "user", "content": prompt}],
        )
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Claude API error: {exc}")

    try:
        data = parse_llm_json(response.content[0].text)
    except ValueError as exc:
        raise HTTPException(status_code=502, detail=f"Failed to parse Claude response: {exc}")

    return {
        "severity_hint": data.get("severity_hint", "medium"),
        "error_category": data.get("error_category", "Unknown"),
        "affected_component": data.get("affected_component"),
        "summary": data.get("summary"),
        "relevant_logs": data.get("relevant_logs", []),
        "ready_for_analysis": data.get("ready_for_analysis", True),
    }


# ── Parsers ────────────────────────────────────────────────────────────────

def _airflow(p: dict) -> dict:
    log = p.get("log", "")
    log_excerpt = "\n".join(log[-30:]) if isinstance(log, list) else str(log)[-2000:]
    return {
        "job_name": f"{p.get('dag_id', 'unknown')}.{p.get('task_id', 'unknown')}",
        "error_message": p.get("exception", "No exception provided"),
        "log_excerpt": log_excerpt,
        "timestamp": p.get("execution_date", datetime.utcnow().isoformat()),
        "run_id": p.get("run_id"),
        "environment": p.get("environment", "production"),
    }


def _dbt(p: dict) -> dict:
    steps = p.get("runSteps", [])
    failed = next((s for s in steps if s.get("status") == "error"), {})
    logs = failed.get("logs", p.get("logs", "No log output"))
    log_excerpt = "\n".join(logs[-30:]) if isinstance(logs, list) else str(logs)[-2000:]
    return {
        "job_name": p.get("jobName", "unknown_job"),
        "error_message": failed.get("statusMessage", p.get("statusMessage", "dbt run failed")),
        "log_excerpt": log_excerpt,
        "timestamp": p.get("runStartedAt", datetime.utcnow().isoformat()),
        "run_id": str(p.get("runId", "")),
        "environment": p.get("environmentName", "production"),
    }


def _fivetran(p: dict) -> dict:
    data = p.get("data", {})
    connector = p.get("connector_name", p.get("connector_id", "unknown"))
    schema = p.get("schema_name", "")
    return {
        "job_name": f"{connector}/{schema}" if schema else connector,
        "error_message": data.get("failure_message") or data.get("reason", "Fivetran sync failed"),
        "log_excerpt": str(data.get("message", ""))[-2000:],
        "timestamp": p.get("created", datetime.utcnow().isoformat()),
        "run_id": data.get("task_id"),
        "environment": p.get("environment", "production"),
    }