import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import os
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError
from models import DiagnosisResult, OwnerInfo
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Notification Agent")

_SLACK_TOKEN = os.environ.get("SLACK_BOT_TOKEN", "")
_slack = WebClient(token=_SLACK_TOKEN) if _SLACK_TOKEN else None

_SEVERITY_EMOJI = {
    "high":   ":red_circle:",
    "medium": ":large_yellow_circle:",
    "low":    ":large_green_circle:",
}
_CONFIDENCE_LABEL = {
    "high":   ":white_check_mark: High",
    "medium": ":question: Medium",
    "low":    ":warning: Low",
}


class NotifyRequest(BaseModel):
    diagnosis: DiagnosisResult
    owner: OwnerInfo
    slack_channel: str = "#data-alerts"


@app.get("/health")
def health():
    slack_ok = "connected" if _SLACK_TOKEN else "no token — console fallback active"
    return {"status": "ok", "service": "notification", "port": 8004, "slack": slack_ok}


@app.post("/notify")
def notify(request: NotifyRequest):
    d = request.diagnosis
    channel = os.environ.get("SLACK_CHANNEL", request.slack_channel)
    blocks = _build_blocks(d, request.owner)
    fallback = (
        f"[{d.severity.upper()}] {d.tool.upper()} failure in {d.job_name} "
        f"({d.environment}) — {d.root_cause[:200]}"
    )

    if not _slack:
        _console_fallback(channel, d, request.owner)
        return {"ok": True, "channel": channel, "ts": None, "mode": "console"}

    try:
        resp = _slack.chat_postMessage(channel=channel, text=fallback, blocks=blocks)
        return {"ok": True, "ts": resp["ts"], "channel": resp["channel"], "mode": "slack"}
    except SlackApiError as exc:
        raise HTTPException(status_code=502, detail=f"Slack error: {exc.response['error']}")


def _build_blocks(d: DiagnosisResult, owner: OwnerInfo) -> list:
    emoji = _SEVERITY_EMOJI.get(d.severity, ":white_circle:")
    confidence = _CONFIDENCE_LABEL.get(d.confidence, d.confidence)

    blocks = [
        {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{emoji}  Pipeline Failure — {d.job_name}"},
        },
        {"type": "divider"},
        # Metadata grid — uses all enriched fields from Agents 1 & 2
        {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*Tool:*\n{d.tool.upper()}"},
                {"type": "mrkdwn", "text": f"*Environment:*\n{d.environment}"},
                {"type": "mrkdwn", "text": f"*Error Category:*\n{d.error_category or 'Unknown'}"},
                {"type": "mrkdwn", "text": f"*Affected Component:*\n{d.affected_component or 'Unknown'}"},
                {"type": "mrkdwn", "text": f"*Severity:*\n{d.severity.capitalize()}"},
                {"type": "mrkdwn", "text": f"*Owner:*\n{owner.slack_handle}"},
            ],
        },
        {"type": "divider"},
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*:mag: Root Cause*\n{d.root_cause}"},
        },
        {
            "type": "section",
            "text": {"type": "mrkdwn", "text": f"*:wrench: Suggested Fix*\n{d.suggested_fix}"},
        },
        {"type": "divider"},
        # Footer — confidence, run ID, timestamp
        {
            "type": "context",
            "elements": [
                {"type": "mrkdwn", "text": _footer(d, owner, confidence)},
            ],
        },
    ]

    return blocks


def _footer(d: DiagnosisResult, owner: OwnerInfo, confidence: str) -> str:
    parts = [
        f"Diagnosed by PipelineDoc AI",
        f"Confidence: {confidence}",
        f"Tagging {owner.slack_handle}",
    ]
    if d.run_id:
        parts.append(f"Run: `{d.run_id}`")
    if d.timestamp:
        parts.append(f"Failed at: {d.timestamp}")
    return "  ·  ".join(parts)


def _console_fallback(channel: str, d: DiagnosisResult, owner: OwnerInfo):
    """Prints the notification to stdout when no Slack token is configured."""
    sep = "=" * 60
    print(f"\n{sep}")
    print(f"[NOTIFICATION → {channel}]")
    print(f"  Job:       {d.job_name}  ({d.tool.upper()} / {d.environment})")
    print(f"  Category:  {d.error_category or 'Unknown'}")
    print(f"  Component: {d.affected_component or 'Unknown'}")
    print(f"  Severity:  {d.severity.upper()}  |  Confidence: {d.confidence.upper()}")
    print(f"  Owner:     {owner.name} ({owner.slack_handle})")
    print(f"\n  ROOT CAUSE\n  {d.root_cause}")
    print(f"\n  SUGGESTED FIX\n  {d.suggested_fix}")
    if d.run_id:
        print(f"\n  Run ID: {d.run_id}")
    print(sep)