"""The Investigator agent (Person 3's deliverable).

Given a ``TriageObject``, gather evidence with tools and return a ``Diagnosis``.

Two engines, one interface:

  * ``_investigate_with_llm`` — a manual Claude tool-use loop. The model drives:
    it calls investigation tools, reads results, and finally calls
    ``submit_diagnosis`` to stop. Used when an Anthropic API key is available.

  * ``_investigate_deterministic`` — a rule-based investigator that calls the
    same tools in a fixed, sensible order and synthesizes a Diagnosis from what
    they return. No network, fully reproducible. This is the "hardcoded-tool
    version" — it ships first and is the fallback whenever the LLM path is
    unavailable or errors out.

Both paths produce an identical ``Diagnosis`` object, use the same confidence
scorer, and satisfy the acceptance test: *given a mocked triage object, call at
least two tools and return a valid Diagnosis.*
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from typing import Any

from . import confidence, prompts, tools
from .contracts import Category, Diagnosis, Evidence, TriageObject

DEFAULT_MODEL = "claude-opus-4-8"



@dataclass
class InvestigatorConfig:
    model: str = DEFAULT_MODEL
    max_iterations: int = 6          
    use_llm: bool | None = None      
    api_key: str | None = None       

    def llm_available(self) -> bool:
        if self.use_llm is not None:
            return self.use_llm
        return bool(self.api_key or os.environ.get("ANTHROPIC_API_KEY"))



@dataclass
class _Trace:
    tools_used: list[str] = field(default_factory=list)
    evidence: list[Evidence] = field(default_factory=list)
    reasoning_steps: list[str] = field(default_factory=list)
    related_past_incidents: list[str] = field(default_factory=list)
    matched_past_incident: bool = False
    pinpointed_location: bool = False

    def record_tool(self, name: str, tool_input: dict[str, Any], result: dict[str, Any]) -> None:
        """Log a tool call and derive evidence/flags from its result."""
        self.tools_used.append(name)
        self.reasoning_steps.append(f"called {name}({_fmt_args(tool_input)})")

        if name == "query_past_incidents" and result.get("found"):
            self.matched_past_incident = True
            for inc in result.get("incidents", []):
                self.related_past_incidents.append(inc["id"])
                self.evidence.append(Evidence(
                    source=name,
                    detail=f"matched past incident {inc['id']}: {inc['root_cause']}",
                    snippet=inc.get("fix", ""),
                ))
        elif name == "read_code" and result.get("found"):
            self.pinpointed_location = True
            self.evidence.append(Evidence(
                source=name,
                detail=f"inspected {result['file']}:{result['line']}",
                snippet=result.get("snippet", ""),
            ))
        elif name == "get_recent_deploys" and result.get("found") and result.get("deploys"):
            top = result["deploys"][0]
            self.pinpointed_location = True
            self.evidence.append(Evidence(
                source=name,
                detail=f"most recent deploy: {top['commit']} by {top['author']} — {top['message']}",
                snippet=str(top),
            ))
        elif name == "check_dependency_health" and result.get("found"):
            if result.get("status") == "down":
                self.pinpointed_location = True
            self.evidence.append(Evidence(
                source=name,
                detail=f"{result['service']} is {result.get('status')}: {result.get('detail', '')}",
                snippet="",
            ))
        elif name == "search_logs" and result.get("found"):
            self.evidence.append(Evidence(
                source=name,
                detail=f"{result['match_count']} log line(s) matched '{result['pattern']}'",
                snippet="\n".join(result.get("matches", [])[:3]),
            ))


def _fmt_args(d: dict[str, Any]) -> str:
    return ", ".join(f"{k}={v!r}" for k, v in d.items())




class Investigator:
    def __init__(self, config: InvestigatorConfig | None = None):
        self.config = config or InvestigatorConfig()

    def investigate(self, triage: TriageObject) -> Diagnosis:
        """Run the investigation and return a Diagnosis. Never raises: if the LLM
        path fails, it falls back to the deterministic engine."""
        if self.config.llm_available():
            try:
                return self._investigate_with_llm(triage)
            except Exception as exc:  
               
                diag = self._investigate_deterministic(triage)
                diag.reasoning_steps.insert(
                    0, f"LLM path failed ({type(exc).__name__}: {exc}); used deterministic fallback")
                return diag
        return self._investigate_deterministic(triage)

    

    def _investigate_with_llm(self, triage: TriageObject) -> Diagnosis:
        import anthropic  

        client = anthropic.Anthropic(api_key=self.config.api_key) if self.config.api_key \
            else anthropic.Anthropic()

        trace = _Trace()
        tool_schemas = [t.to_anthropic_schema() for t in tools.all_tools()]
        messages: list[dict[str, Any]] = [
            {"role": "user", "content": prompts.build_initial_user_message(triage)}
        ]

        submitted: dict[str, Any] | None = None

        for _ in range(self.config.max_iterations):
            response = client.messages.create(
                model=self.config.model,
                max_tokens=4096,
                system=prompts.SYSTEM_PROMPT,
                thinking={"type": "adaptive", "display": "summarized"},
                tools=tool_schemas,
                messages=messages,
            )
            
            messages.append({"role": "assistant", "content": response.content})

            
            for block in response.content:
                if block.type == "thinking" and getattr(block, "thinking", ""):
                    trace.reasoning_steps.append(f"[thinking] {block.thinking.strip()}")
                elif block.type == "text" and block.text.strip():
                    trace.reasoning_steps.append(block.text.strip())

            tool_uses = [b for b in response.content if b.type == "tool_use"]
            if not tool_uses:
               
                if response.stop_reason == "end_turn":
                    messages.append({"role": "user", "content":
                                     "Call submit_diagnosis now with your best conclusion."})
                    continue
                break

            
            tool_results = []
            for tu in tool_uses:
                if tu.name == "submit_diagnosis":
                    submitted = dict(tu.input)
                    tool_results.append({
                        "type": "tool_result", "tool_use_id": tu.id,
                        "content": tools.as_json({"accepted": True}),
                    })
                    continue
                result = tools.execute(tu.name, dict(tu.input))
                trace.record_tool(tu.name, dict(tu.input), result)
                tool_results.append({
                    "type": "tool_result", "tool_use_id": tu.id,
                    "content": tools.as_json(result),
                })
            messages.append({"role": "user", "content": tool_results})

            if submitted is not None:
                break

        if submitted is not None:
            return self._finalize(triage, trace, submitted, model=self.config.model)

       
        trace.reasoning_steps.append(
            f"reached max_iterations ({self.config.max_iterations}) without submit_diagnosis")
        return self._synthesize_from_trace(triage, trace, model=self.config.model,
                                            forced=True)

   

    def _investigate_deterministic(self, triage: TriageObject) -> Diagnosis:
        """Rule-based investigation: a fixed, sensible tool order per category."""
        trace = _Trace()
        md = triage.metadata or {}
        category = self._infer_category(triage)

        
        self._call(trace, "query_past_incidents",
                   {"error_signature": triage.error_signature})

        
        self._call(trace, "search_logs",
                   {"pattern": self._log_needle(triage), "job_id": triage.job_id})

       
        if category == Category.DEPENDENCY:
            dep = md.get("dependency") or self._guess_dependency(triage)
            if dep:
                self._call(trace, "check_dependency_health", {"service": dep})
        elif category == Category.CODE:
            f, line = md.get("error_file"), md.get("error_line")
            if f and line:
                self._call(trace, "read_code", {"file": f, "line": int(line)})
            if md.get("service"):
                self._call(trace, "get_recent_deploys", {"service": md["service"]})
        elif category == Category.CONFIG:
           
          
            if md.get("service"):
                self._call(trace, "get_recent_deploys", {"service": md["service"]})

        return self._synthesize_from_trace(triage, trace, category=category,
                                           model="deterministic-fallback")

    def _call(self, trace: _Trace, name: str, tool_input: dict[str, Any]) -> dict[str, Any]:
        result = tools.execute(name, tool_input)
        trace.record_tool(name, tool_input, result)
        return result

    

    def _finalize(self, triage: TriageObject, trace: _Trace,
                  submitted: dict[str, Any], model: str) -> Diagnosis:
        """Build a Diagnosis from the model's submit_diagnosis payload, adjusting
        confidence against the evidence heuristic."""
        category = Category.coerce(submitted.get("category", triage.category))
        model_conf = float(submitted.get("confidence", 0.5))
        heuristic = confidence.heuristic_score(
            category=category, tools_used=trace.tools_used, evidence=trace.evidence,
            matched_past_incident=trace.matched_past_incident,
            pinpointed_location=trace.pinpointed_location,
        )
        final_conf = confidence.blend(model_conf, heuristic)
        needs_human = bool(submitted.get("needs_human", False)) or final_conf < 0.45

        trace.reasoning_steps.append(
            f"confidence: model={model_conf:.2f} heuristic={heuristic:.2f} -> {final_conf:.2f}")

        return Diagnosis(
            incident_id=triage.incident_id,
            root_cause=submitted.get("root_cause", "undetermined"),
            category=category,
            confidence=final_conf,
            summary=submitted.get("summary") or _one_liner(submitted.get("root_cause", "")),
            recommended_fix=submitted.get("recommended_fix", ""),
            suggested_owner=submitted.get("suggested_owner") or self._owner_from_evidence(trace),
            evidence=trace.evidence,
            related_past_incidents=trace.related_past_incidents,
            tools_used=trace.tools_used,
            reasoning_steps=trace.reasoning_steps,
            needs_human=needs_human,
            model=model,
        )

    def _synthesize_from_trace(self, triage: TriageObject, trace: _Trace,
                               category: Category | None = None,
                               model: str = "deterministic-fallback",
                               forced: bool = False) -> Diagnosis:
        """Build a Diagnosis purely from gathered evidence (no model verdict).

        Used by the deterministic engine and by the LLM engine when it runs out
        of iterations. Prefers a matched past incident's recorded cause/fix.
        """
        category = category or self._infer_category(triage)
        past = self._best_past_incident(trace)

        if past:
            root_cause = past["root_cause"]
            recommended_fix = past["fix"]
            suggested_owner = past.get("owner")
            category = Category.coerce(past.get("category", category))
        else:
            root_cause, recommended_fix, suggested_owner = self._rule_synthesis(
                triage, trace, category)

        heuristic = confidence.heuristic_score(
            category=category, tools_used=trace.tools_used, evidence=trace.evidence,
            matched_past_incident=trace.matched_past_incident,
            pinpointed_location=trace.pinpointed_location,
        )
        if forced:
            heuristic = min(heuristic, 0.5) 
        needs_human = heuristic < 0.45 or category == Category.UNKNOWN

        trace.reasoning_steps.append(f"synthesized diagnosis; confidence={heuristic:.2f}")

        return Diagnosis(
            incident_id=triage.incident_id,
            root_cause=root_cause,
            category=category,
            confidence=heuristic,
            summary=_one_liner(root_cause),
            recommended_fix=recommended_fix,
            suggested_owner=suggested_owner or self._owner_from_evidence(trace),
            evidence=trace.evidence,
            related_past_incidents=trace.related_past_incidents,
            tools_used=trace.tools_used,
            reasoning_steps=trace.reasoning_steps,
            needs_human=needs_human,
            model=model,
        )

    

    def _rule_synthesis(self, triage: TriageObject, trace: _Trace,
                        category: Category) -> tuple[str, str, str | None]:
        """Fallback root-cause/fix when no past incident matched."""
        md = triage.metadata or {}
        if category == Category.DEPENDENCY:
            dep = md.get("dependency") or self._guess_dependency(triage) or "a downstream service"
            down = any(e.source == "check_dependency_health" and "down" in e.detail
                       for e in trace.evidence)
            cause = (f"{triage.job_id} failed because its dependency {dep} was unreachable"
                     + (" (health check reports it is down)." if down else "."))
            fix = (f"Confirm {dep} is back up, then re-run {triage.job_id}. Longer term add a "
                   "pre-flight health check so the job skips (rather than hard-fails) during outages.")
            return cause, fix, "platform-oncall"
        if category == Category.CODE:
            loc = md.get("error_file")
            deploy = next((e for e in trace.evidence if e.source == "get_recent_deploys"), None)
            cause = f"A code error ({triage.error_signature}) in {triage.job_id}"
            if loc:
                cause += f" at {loc}:{md.get('error_line')}"
            if deploy:
                cause += f", likely introduced by the most recent deploy ({deploy.detail})"
            cause += "."
            fix = "Fix or guard the failing code path; if a recent deploy caused it, roll back and patch."
            return cause, fix, None
        if category == Category.CONFIG:
            var = md.get("missing_env")
            cause = (f"{triage.job_id} is missing required configuration"
                     + (f" (environment variable {var})." if var else "."))
            fix = (f"Set {var} for the job" if var else "Provide the missing configuration") \
                + " (check for a recent secrets/config migration that dropped it)."
            return cause, fix, "platform-oncall"
        return (f"Could not determine a specific root cause for {triage.error_signature}.",
                "Escalate to a human on-call engineer with the gathered evidence.", None)

    def _infer_category(self, triage: TriageObject) -> Category:
        if triage.category != Category.UNKNOWN:
            return triage.category
        blob = f"{triage.error_signature} {triage.error_excerpt}".lower()
        if any(k in blob for k in ("connection refused", "timeout", "unreachable",
                                   "operationalerror", "503", "econnrefused")):
            return Category.DEPENDENCY
        if any(k in blob for k in ("environment variable", "keyerror", "config", "secret",
                                   "not set", "missing required")):
            return Category.CONFIG
        if any(k in blob for k in ("traceback", "error:", "exception", "attributeerror",
                                   "typeerror", "valueerror", "nonetype")):
            return Category.CODE
        if any(k in blob for k in ("out of memory", "oom", "disk full", "evicted", "killed")):
            return Category.INFRA
        return Category.UNKNOWN

    def _log_needle(self, triage: TriageObject) -> str:
        """A short, high-signal substring to grep the log with."""
        text = triage.error_excerpt or triage.error_signature
        for token in ("connection refused", "AttributeError", "environment variable",
                      "KeyError", "OperationalError", "ERROR"):
            if token.lower() in text.lower():
                return token
        return "ERROR"

    def _guess_dependency(self, triage: TriageObject) -> str | None:
        blob = f"{triage.error_signature} {triage.error_excerpt}".lower()
        for dep in ("orders-db", "sendgrid"):
            if dep in blob:
                return dep
        return None

    def _best_past_incident(self, trace: _Trace) -> dict[str, Any] | None:
       
        if not trace.related_past_incidents:
            return None
        from . import mock_data
        wanted = set(trace.related_past_incidents)
        for inc in mock_data.PAST_INCIDENTS:
            if inc["id"] in wanted:
                return inc
        return None

    def _owner_from_evidence(self, trace: _Trace) -> str | None:
        past = self._best_past_incident(trace)
        return past.get("owner") if past else None


def _one_liner(text: str) -> str:
    text = " ".join(text.split())
    return text if len(text) <= 120 else text[:117] + "..."




def investigate(triage: TriageObject, **config_kwargs: Any) -> Diagnosis:
    """One-call helper: ``investigate(triage_object)`` -> ``Diagnosis``."""
    return Investigator(InvestigatorConfig(**config_kwargs)).investigate(triage)