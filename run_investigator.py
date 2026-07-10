"""Demo / manual driver for the Investigator agent (Person 3).

    python run_investigator.py                 # run all three demo scenarios
    python run_investigator.py dependency      # run one scenario
    python run_investigator.py --json          # print Diagnosis as JSON

Auto-uses the Claude tool-use loop when ANTHROPIC_API_KEY is set, otherwise the
deterministic offline engine. Add --deterministic to force the offline engine.
"""

from __future__ import annotations

import argparse
import json
import os
import sys


for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except (AttributeError, ValueError):
        pass

from investigator import Investigator, InvestigatorConfig
from investigator.contracts import Diagnosis
from investigator.mock_data import demo_triage_objects


def _print_pretty(diag: Diagnosis) -> None:
    bar = "-" * 68
    print(bar)
    print(f"  incident   : {diag.incident_id}")
    print(f"  category   : {diag.category.value}")
    print(f"  confidence : {diag.confidence:.2f} ({diag.confidence_label})"
          f"{'  [!] NEEDS HUMAN' if diag.needs_human else ''}")
    print(f"  engine     : {diag.model}")
    print(bar)
    print(f"  ROOT CAUSE : {diag.root_cause}")
    print(f"  FIX        : {diag.recommended_fix}")
    if diag.suggested_owner:
        print(f"  OWNER      : {diag.suggested_owner}")
    if diag.related_past_incidents:
        print(f"  RELATED    : {', '.join(diag.related_past_incidents)}")
    print(f"  TOOLS USED : {', '.join(diag.tools_used) or '(none)'}")
    print("  EVIDENCE   :")
    for e in diag.evidence:
        print(f"    - [{e.source}] {e.detail}")
    print(bar)
    print()


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the Investigator agent on demo scenarios.")
    parser.add_argument("scenario", nargs="?", choices=["dependency", "code", "config"],
                        help="run a single scenario (default: all three)")
    parser.add_argument("--json", action="store_true", help="print Diagnosis as JSON")
    parser.add_argument("--deterministic", action="store_true",
                        help="force the offline deterministic engine")
    args = parser.parse_args()

    cfg = InvestigatorConfig(use_llm=False) if args.deterministic else InvestigatorConfig()
    agent = Investigator(cfg)

    engine = "deterministic (offline)" if not cfg.llm_available() else f"Claude ({cfg.model})"
    print(f"\nInvestigator engine: {engine}\n", file=sys.stderr)

    scenarios = demo_triage_objects()
    selected = {args.scenario: scenarios[args.scenario]} if args.scenario else scenarios

    for name, triage in selected.items():
        diag = agent.investigate(triage)
        if args.json:
            print(json.dumps(diag.to_dict(), indent=2))
        else:
            print(f"### scenario: {name}")
            _print_pretty(diag)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())