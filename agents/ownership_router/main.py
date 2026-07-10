import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import fnmatch
import yaml
from fastapi import FastAPI
from pydantic import BaseModel
from models import OwnerInfo
from dotenv import load_dotenv

load_dotenv()

app = FastAPI(title="Ownership Router Agent")

_OWNERS_FILE = Path(__file__).parent.parent.parent / "pipeline_owners.yaml"


class RouteRequest(BaseModel):
    job_name: str


@app.get("/health")
def health():
    return {"status": "ok", "service": "ownership-router", "port": 8003}


@app.post("/route", response_model=OwnerInfo)
def route(request: RouteRequest):
    config = yaml.safe_load(_OWNERS_FILE.read_text())
    job_lower = request.job_name.lower()

    for entry in config.get("pipelines", []):
        if fnmatch.fnmatch(job_lower, entry["pattern"].lower()):
            return OwnerInfo(
                name=entry["name"],
                slack_handle=entry["slack_handle"],
                team=entry.get("team"),
            )

    return OwnerInfo(**config["default_owner"])