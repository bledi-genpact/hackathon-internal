# PipelineDoc AI

> AI-powered incident response for data pipelines — automatic root cause analysis, owner routing, and Slack alerts in seconds.

Built at the **Genpact App Modernization Hackathon · July 2026**

---

## What It Does

When a data pipeline fails (dbt Cloud, Apache Airflow, Fivetran), PipelineDoc AI automatically:

1. **Parses & enriches the error** — strips noise, classifies the failure type, identifies the affected component
2. **Diagnoses the root cause** — explains *why* it failed in plain English, with a step-by-step fix and severity rating
3. **Routes to the right owner** — matches the job name against a YAML ownership map, no guessing
4. **Sends a Slack alert** — rich Block Kit message with everything the on-call engineer needs

All four steps are wired together by an orchestrator that runs diagnosis and ownership lookup in parallel, keeping the total round-trip fast.

---

## Architecture

```
[Pipeline Webhook]
       │
       ▼
[Orchestrator  :8000]
       │
       ├──► [Agent 1 · Log Collector  :8001]   Claude claude-sonnet-4-6  — log enrichment
       │              │
       ├──► [Agent 2 · Diagnosis      :8002]   Claude claude-sonnet-4-6  — root cause analysis  ┐ parallel
       ├──► [Agent 3 · Ownership Router:8003]  YAML rule lookup (no AI)                          ┘
       │
       └──► [Agent 4 · Notification   :8004]   Slack Block Kit / console fallback

[Streamlit Dashboard :8501]  — real-time pipeline visualization & demo UI
```

The **Investigator module** (`investigator/`) is a self-contained component that slots between a Triage agent and an Explainer agent in the broader multi-team pipeline:

```
Triage ──TriageObject──► Investigator ──Diagnosis──► Explainer
```

---

## Tech Stack

| Layer | Technology |
|---|---|
| Language | Python 3.12 |
| Agent services | FastAPI + Uvicorn |
| Dashboard | Streamlit 1.41 |
| AI model | Anthropic Claude (`claude-sonnet-4-6`, `claude-opus-4-8`) |
| Slack integration | slack-sdk 3.27 (Block Kit) |
| HTTP client | httpx (async) |
| Config | PyYAML + python-dotenv |
| Data validation | Pydantic |

---

## Project Structure

```
hackathon-internal/
├── orchestrator/main.py          # Orchestrator service (port 8000)
├── agents/
│   ├── log_collector/main.py     # Agent 1 — log parsing & Claude enrichment
│   ├── diagnosis/main.py         # Agent 2 — root cause analysis
│   ├── ownership_router/main.py  # Agent 3 — job-to-owner YAML lookup
│   └── notification/main.py      # Agent 4 — Slack alert sender
├── investigator/
│   ├── investigator.py           # Core Investigator class (LLM + deterministic engines)
│   ├── contracts.py              # TriageObject / Diagnosis data contracts
│   ├── tools.py                  # Investigation tools (logs, deploys, past incidents)
│   ├── confidence.py             # Confidence scoring (model self-report + heuristics)
│   ├── prompts.py                # System prompt & message builder
│   └── mock_data.py              # Offline fixtures for local development
├── frontend/app.py               # Streamlit dashboard
├── demo/
│   ├── simulate_failure.py       # CLI test harness
│   └── sample_logs/              # dbt / Airflow / Fivetran sample payloads
├── models.py                     # Shared Pydantic models
├── utils.py                      # LLM JSON parsing helpers
├── pipeline_owners.yaml          # Ownership routing config
├── requirements.txt
└── start_all.bat                 # One-click launcher (Windows)
```

---

## Getting Started

### Prerequisites

- Python 3.12+
- An Anthropic API key
- (Optional) A Slack bot token for real Slack notifications

### 1. Install dependencies

```bash
pip install -r requirements.txt
```

### 2. Configure environment

Create a `.env` file in the project root:

```env
ANTHROPIC_API_KEY=sk-ant-...

# Optional — omit to print Slack messages to the console instead
SLACK_BOT_TOKEN=xoxb-...
SLACK_CHANNEL=#data-alerts

# Optional — override default service URLs
LOG_COLLECTOR_URL=http://localhost:8001
DIAGNOSIS_URL=http://localhost:8002
OWNERSHIP_ROUTER_URL=http://localhost:8003
NOTIFICATION_URL=http://localhost:8004
```

### 3. Start all services

**Windows (one command):**
```bat
start_all.bat
```

This opens six terminal windows — one per service plus the Streamlit dashboard.

**Manual start (any platform):**
```bash
# Terminal 1
uvicorn orchestrator.main:app --port 8000

# Terminal 2
uvicorn agents.log_collector.main:app --port 8001

# Terminal 3
uvicorn agents.diagnosis.main:app --port 8002

# Terminal 4
uvicorn agents.ownership_router.main:app --port 8003

# Terminal 5
uvicorn agents.notification.main:app --port 8004

# Terminal 6
streamlit run frontend/app.py
```

### 4. Open the dashboard

Visit [http://localhost:8501](http://localhost:8501)

---

## Running a Demo

### Via the Streamlit UI

1. Open the dashboard at `localhost:8501`
2. Select a pipeline tool (dbt Cloud, Airflow, or Fivetran)
3. Click **Simulate Failure**
4. Watch the four-agent pipeline run in real time — each stage lights up as it completes
5. See the plain-English root cause, suggested fix, owner, and Slack message preview

### Via the CLI

```bash
python demo/simulate_failure.py dbt
python demo/simulate_failure.py airflow
python demo/simulate_failure.py fivetran
```

### Pre-built failure scenarios

| Scenario | Job | Error type | Root cause |
|---|---|---|---|
| **dbt Cloud** | `finance_monthly_close` | Schema mismatch | `PROD_DB.RAW.STRIPE_CHARGES` table missing — upstream Fivetran sync likely failed |
| **Airflow** | `etl_salesforce_daily` | Authentication failure | Snowflake connection key cannot be decoded — expired or rotated credentials |

---

## Ownership Routing

Edit `pipeline_owners.yaml` to map job name patterns to owners. First match wins. Example:

```yaml
owners:
  - pattern: "finance_*"
    name: Alice Johnson
    slack_handle: "@alice.johnson"
    team: Finance Analytics

  - pattern: "etl_salesforce*"
    name: Bob Chen
    slack_handle: "@bob.chen"
    team: Revenue Operations

  - pattern: "*"          # catch-all
    name: On-Call Engineer
    slack_handle: "@data-oncall"
    team: Data Engineering
```

---

## Investigator Module

The `investigator/` module is a standalone component with its own architecture, designed to be composed into a larger multi-agent pipeline.

### Key design decisions

- **Two engines:** an LLM engine (Claude `claude-opus-4-8` with adaptive thinking and tool use) and a deterministic fallback that applies fixed rules without any network calls
- **Confidence blending:** final confidence = 40% model self-report + 60% heuristic evidence score
- **Stop tool pattern:** the LLM calls `submit_diagnosis` when it has enough evidence — not when it runs out of tokens
- **Five investigation tools:** `query_past_incidents`, `search_logs`, `read_code`, `get_recent_deploys`, `check_dependency_health`

### Running the investigator standalone

```bash
python run_investigator.py
```

### Running tests

```bash
pytest tests/test_investigator.py -v
```

Tests include unit, acceptance, contract, and LLM-engine tests. The LLM-engine tests use a fake Anthropic client so they run fully offline.

---

## API Reference

All services expose a single `POST /analyze` endpoint.

### Orchestrator (`POST http://localhost:8000/analyze`)

```json
{
  "tool": "dbt",
  "payload": { /* raw webhook JSON from dbt Cloud / Airflow / Fivetran */ }
}
```

**Response:**
```json
{
  "job_name": "finance_monthly_close",
  "error_category": "schema_mismatch",
  "affected_component": "PROD_DB.RAW.STRIPE_CHARGES",
  "root_cause": "The source table referenced in the dbt model does not exist...",
  "suggested_fix": "1. Check the Fivetran sync status for the Stripe connector...",
  "severity": "high",
  "confidence": 0.87,
  "owner": { "name": "Alice Johnson", "slack_handle": "@alice.johnson", "team": "Finance Analytics" },
  "timing": { "log_collection_ms": 1240, "diagnosis_ms": 2180, "routing_ms": 45, "notification_ms": 310 }
}
```

---

## Team

Built by the Genpact App Modernization Hackathon team · July 2026

| Role | Deliverable |
|---|---|
| Person 1 | Log Collector agent + Orchestrator |
| Person 2 | Triage agent (upstream, feeds Investigator) |
| Person 3 | Investigator module |
| Person 4 | Explainer agent (downstream, consumes Investigator) |
