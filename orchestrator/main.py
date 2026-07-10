import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

import asyncio
import os
import time
import httpx
from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="PipelineDoc Orchestrator")

LOG_COLLECTOR = os.getenv("LOG_COLLECTOR_URL",  "http://localhost:8001")
DIAGNOSIS     = os.getenv("DIAGNOSIS_URL",       "http://localhost:8002")
OWNERSHIP     = os.getenv("OWNERSHIP_URL",       "http://localhost:8003")
NOTIFICATION  = os.getenv("NOTIFICATION_URL",    "http://localhost:8004")

TIMEOUT = httpx.Timeout(120.0)

_SERVICES = {
    "log-collector":     f"{LOG_COLLECTOR}/health",
    "diagnosis":         f"{DIAGNOSIS}/health",
    "ownership-router":  f"{OWNERSHIP}/health",
    "notification":      f"{NOTIFICATION}/health",
}


class FailureRequest(BaseModel):
    tool: str
    raw_payload: dict
    slack_channel: str = "#data-alerts"


@app.get("/health")
async def health():
    """Ping every downstream service and report their status."""
    async with httpx.AsyncClient(timeout=httpx.Timeout(5.0)) as client:
        async def _ping(name: str, url: str):
            try:
                r = await client.get(url)
                return name, r.status_code == 200, r.json()
            except Exception as exc:
                return name, False, {"error": str(exc)}

        results = await asyncio.gather(*[_ping(n, u) for n, u in _SERVICES.items()])

    services = {name: {"ok": ok, "detail": detail} for name, ok, detail in results}
    all_ok = all(v["ok"] for v in services.values())
    return {
        "status": "ok" if all_ok else "degraded",
        "orchestrator": {"ok": True, "port": 8000},
        "services": services,
    }


@app.post("/failure")
async def handle_failure(request: FailureRequest):
    t_start = time.perf_counter()

    async with httpx.AsyncClient(timeout=TIMEOUT) as client:

      
        t1 = time.perf_counter()
        r = await client.post(
            f"{LOG_COLLECTOR}/collect",
            json={"tool": request.tool, "raw_payload": request.raw_payload},
        )
        _check(r, "log-collector")
        normalized = r.json()
        t1 = round(time.perf_counter() - t1, 2)

     
        t23 = time.perf_counter()
        (diagnosis_r, ownership_r) = await asyncio.gather(
            client.post(f"{DIAGNOSIS}/diagnose", json=normalized),
            client.post(f"{OWNERSHIP}/route", json={"job_name": normalized["job_name"]}),
        )
        _check(diagnosis_r, "diagnosis")
        _check(ownership_r, "ownership-router")
        diagnosis = diagnosis_r.json()
        owner = ownership_r.json()
        t23 = round(time.perf_counter() - t23, 2)

       
        t4 = time.perf_counter()
        r = await client.post(
            f"{NOTIFICATION}/notify",
            json={
                "diagnosis": diagnosis,
                "owner": owner,
                "slack_channel": request.slack_channel,
            },
        )
        _check(r, "notification")
        notification = r.json()
        t4 = round(time.perf_counter() - t4, 2)

    total = round(time.perf_counter() - t_start, 2)

    return {
        "normalized":   normalized,
        "diagnosis":    diagnosis,
        "owner":        owner,
        "notification": notification,
        "timing": {
            "log_collector_s":  t1,
            "diagnosis_and_owner_s": t23,
            "notification_s":   t4,
            "total_s":          total,
        },
    }


def _check(response: httpx.Response, service: str):
    if response.status_code >= 400:
        raise HTTPException(
            status_code=502,
            detail=f"{service} error {response.status_code}: {response.text}",
        )