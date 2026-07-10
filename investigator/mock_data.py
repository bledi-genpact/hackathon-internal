"""Offline fixtures so the Investigator runs with no network and no real infra.

Two purposes:
  1. Backing data for the mock tool implementations in ``tools.py`` — logs,
     source snippets, deploy history, a past-incident memory table, service health.
  2. Three ready-made TriageObjects (one per failure category) that mirror the
     three deliberately-broken jobs Person 5 builds for the demo.

When the real tools land (Person 1's log store, Person 5's SQLite table), swap
the implementations in ``tools.py`` — nothing else needs to change, because the
tools return the same shaped dicts.
"""

from __future__ import annotations

from .contracts import Category, TriageObject





FULL_LOGS: dict[str, str] = {
    "checkout-nightly": """
2026-07-09T02:14:01Z INFO  starting checkout reconciliation job run=8842
2026-07-09T02:14:02Z INFO  connecting to postgres primary db=orders host=orders-db.internal:5432
2026-07-09T02:14:32Z WARN  connection attempt 1 failed: connection refused
2026-07-09T02:15:02Z WARN  connection attempt 2 failed: connection refused
2026-07-09T02:15:32Z ERROR could not connect to orders-db.internal:5432 after 3 attempts: OperationalError: connection refused
2026-07-09T02:15:32Z ERROR job run=8842 aborted
""".strip(),
    "report-builder": """
2026-07-09T03:01:10Z INFO  report-builder run=1290 started commit=a1b9f3c
2026-07-09T03:01:11Z INFO  loading 4211 user records
2026-07-09T03:01:12Z ERROR Traceback (most recent call last):
  File "/app/report/build.py", line 88, in summarize
    total = sum(u.spend for u in users)
  File "/app/report/build.py", line 88, in <genexpr>
    total = sum(u.spend for u in users)
AttributeError: 'NoneType' object has no attribute 'spend'
2026-07-09T03:01:12Z ERROR report-builder run=1290 failed
""".strip(),
    "email-digest": """
2026-07-09T06:00:00Z INFO  email-digest run=555 booting
2026-07-09T06:00:00Z INFO  reading configuration
2026-07-09T06:00:00Z ERROR missing required environment variable SENDGRID_API_KEY
2026-07-09T06:00:00Z ERROR KeyError: 'SENDGRID_API_KEY'
2026-07-09T06:00:00Z ERROR email-digest run=555 could not start
""".strip(),
}


SOURCE_SNIPPETS: dict[str, str] = {
    "/app/report/build.py:88": (
        "  85  def summarize(users):\n"
        "  86      # users comes straight from the DB fetch; some rows are archived\n"
        "  87      # and come back as None — added in commit a1b9f3c, not filtered here\n"
        "  88      total = sum(u.spend for u in users)   # <-- u can be None\n"
        "  89      return total\n"
    ),
}


DEPLOY_HISTORY: dict[str, list[dict]] = {
    "report-builder": [
        {"commit": "a1b9f3c", "author": "priya", "when": "2026-07-09T01:40:00Z",
         "message": "include archived users in report query"},
        {"commit": "9f2e1aa", "author": "sam", "when": "2026-07-06T12:00:00Z",
         "message": "bump pandas to 2.2"},
    ],
    "checkout-nightly": [
        {"commit": "77c0de2", "author": "lee", "when": "2026-07-01T09:00:00Z",
         "message": "add retry backoff to db connect"},
    ],
    "email-digest": [
        {"commit": "b4d5e6f", "author": "priya", "when": "2026-07-08T18:20:00Z",
         "message": "migrate secrets to new vault path"},
    ],
}


SERVICE_HEALTH: dict[str, dict] = {
    "orders-db": {"status": "down", "since": "2026-07-09T02:10:00Z",
                  "detail": "primary unreachable; failover did not promote replica"},
    "sendgrid": {"status": "healthy", "since": "2026-07-01T00:00:00Z", "detail": "ok"},
}


PAST_INCIDENTS: list[dict] = [
    {
        "id": "INC-3301",
        "signature_contains": "connection refused",
        "category": "dependency",
        "root_cause": "orders-db primary went down during a maintenance window; "
                      "job had no circuit breaker so it hard-failed",
        "fix": "Wait for orders-db failover, then re-run. Longer term: add a "
               "health pre-check and skip (don't fail) when the DB is in maintenance.",
        "owner": "data-platform",
    },
    {
        "id": "INC-3288",
        "signature_contains": "NoneType",
        "category": "code",
        "root_cause": "unfiltered None rows from a widened DB query hit an "
                      "attribute access",
        "fix": "Filter None rows before the aggregation, or use getattr with a default.",
        "owner": "reporting-team",
    },
    {
        "id": "INC-3270",
        "signature_contains": "environment variable",
        "category": "config",
        "root_cause": "a secret was moved to a new vault path but the job's env "
                      "mapping wasn't updated",
        "fix": "Point the job's env mapping at the new vault path for the secret.",
        "owner": "platform-oncall",
    },
]





def demo_triage_objects() -> dict[str, TriageObject]:
    return {
        "dependency": TriageObject(
            incident_id="INC-9001",
            job_id="checkout-nightly",
            error_signature="OperationalError: connection refused orders-db.internal:5432",
            category=Category.DEPENDENCY,
            severity="high",
            error_excerpt="could not connect to orders-db.internal:5432 after 3 attempts: "
                          "OperationalError: connection refused",
            cleaned_log=FULL_LOGS["checkout-nightly"],
            escalated_reason="No exact signature match in rules table; connection errors "
                             "can be transient or a real outage — needs investigation.",
            metadata={"service": "checkout-nightly", "dependency": "orders-db",
                      "run": "8842"},
        ),
        "code": TriageObject(
            incident_id="INC-9002",
            job_id="report-builder",
            error_signature="AttributeError: 'NoneType' object has no attribute 'spend'",
            category=Category.CODE,
            severity="medium",
            error_excerpt="AttributeError: 'NoneType' object has no attribute 'spend' "
                          "at /app/report/build.py:88",
            cleaned_log=FULL_LOGS["report-builder"],
            escalated_reason="Traceback present; likely a code regression but needs the "
                             "offending commit confirmed.",
            metadata={"service": "report-builder", "commit_sha": "a1b9f3c",
                      "error_file": "/app/report/build.py", "error_line": 88, "run": "1290"},
        ),
        "config": TriageObject(
            incident_id="INC-9003",
            job_id="email-digest",
            error_signature="KeyError: 'SENDGRID_API_KEY' missing environment variable",
            category=Category.UNKNOWN,  
            severity="medium",
            error_excerpt="missing required environment variable SENDGRID_API_KEY",
            cleaned_log=FULL_LOGS["email-digest"],
            escalated_reason="Unclassified by rules table; escalating for root-cause.",
            metadata={"service": "email-digest", "missing_env": "SENDGRID_API_KEY",
                      "run": "555"},
        ),
    }