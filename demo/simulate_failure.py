"""
Fire a simulated pipeline failure at the orchestrator and print the result.

Usage:
    python demo/simulate_failure.py           # defaults to dbt
    python demo/simulate_failure.py airflow
    python demo/simulate_failure.py dbt
    python demo/simulate_failure.py fivetran
"""
import sys
import json
import argparse
from pathlib import Path
import httpx

ORCHESTRATOR = "http://localhost:8000"
SAMPLES = Path(__file__).parent / "sample_logs"

TOOLS = {
    "airflow":  ("airflow",  SAMPLES / "airflow_failure.json"),
    "dbt":      ("dbt",      SAMPLES / "dbt_failure.json"),
    "fivetran": ("fivetran", SAMPLES / "fivetran_failure.json"),
}

parser = argparse.ArgumentParser()
parser.add_argument("tool", nargs="?", default="dbt", choices=list(TOOLS))
parser.add_argument("--channel", default="#data-alerts")
args = parser.parse_args()

tool, sample_file = TOOLS[args.tool]
raw_payload = json.loads(sample_file.read_text())

print(f"\n  Firing {tool.upper()} failure → orchestrator...")
print("  (this takes ~15-30 seconds — two Claude calls in the pipeline)\n")

try:
    resp = httpx.post(
        f"{ORCHESTRATOR}/failure",
        json={"tool": tool, "raw_payload": raw_payload, "slack_channel": args.channel},
        timeout=120,
    )
    resp.raise_for_status()
except httpx.ConnectError:
    print("  ERROR: Cannot reach orchestrator at localhost:8000")
    print("  Run start_all.bat first, wait a few seconds, then retry.")
    sys.exit(1)
except httpx.HTTPStatusError as e:
    print(f"  ERROR {e.response.status_code}: {e.response.text}")
    sys.exit(1)

result = resp.json()
d = result["diagnosis"]
o = result["owner"]
notif = result.get("notification", {})

SEP = "=" * 65
THIN = "-" * 65

print(SEP)
print(f"  JOB        {d['job_name']}")
print(f"  TOOL       {d['tool'].upper()}   |   ENVIRONMENT  {d['environment']}")
print(f"  CATEGORY   {d.get('error_category', 'Unknown')}")
print(f"  COMPONENT  {d.get('affected_component', 'Unknown')}")
print(THIN)
print(f"  SEVERITY   {d['severity'].upper()}   |   CONFIDENCE  {d['confidence'].upper()}")
print(f"  OWNER      {o['name']} ({o['slack_handle']})")
print(SEP)

print(f"\n  ROOT CAUSE")
print(f"  {d['root_cause']}\n")

print(f"  SUGGESTED FIX")
print(f"  {d['suggested_fix']}\n")

mode = notif.get("mode", "unknown")
if mode == "slack":
    print(f"  Slack notification sent to {notif.get('channel')}  (ts: {notif.get('ts')})")
elif mode == "console":
    print(f"  Notification printed to console (no SLACK_BOT_TOKEN configured)")
else:
    print(f"  Notification status: {notif}")

print(SEP)