"""Tests for the Investigator agent (Person 3).

Run:  python -m pytest tests/        (or  python -m unittest discover tests)

These exercise the DETERMINISTIC engine (use_llm=False) so they are fast,
offline, and reproducible. The LLM engine shares the same finalize/synthesis
code and contract, so passing here means the shape is right for both.
"""

from __future__ import annotations

import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from investigator import Investigator, InvestigatorConfig, investigate  # noqa: E402
from investigator.contracts import Category, Diagnosis, TriageObject  # noqa: E402
from investigator import tools  # noqa: E402
from investigator.mock_data import demo_triage_objects  # noqa: E402


def _agent() -> Investigator:
    return Investigator(InvestigatorConfig(use_llm=False))


class AcceptanceTest(unittest.TestCase):
    """The brief's 'Done when': mocked triage -> >=2 tools -> valid Diagnosis."""

    def test_mocked_triage_yields_valid_diagnosis_with_two_tools(self):
        for name, triage in demo_triage_objects().items():
            with self.subTest(scenario=name):
                diag = _agent().investigate(triage)

                self.assertIsInstance(diag, Diagnosis)
                
                distinct = {t for t in diag.tools_used if t != "submit_diagnosis"}
                self.assertGreaterEqual(len(distinct), 2,
                                        f"only used {diag.tools_used}")
                
                self.assertEqual(diag.incident_id, triage.incident_id)
                self.assertTrue(diag.root_cause)
                self.assertTrue(diag.recommended_fix)
                self.assertIsInstance(diag.category, Category)
                self.assertGreaterEqual(diag.confidence, 0.0)
                self.assertLessEqual(diag.confidence, 1.0)
                self.assertIn(diag.confidence_label, ("low", "medium", "high"))


class CategoryTest(unittest.TestCase):
    def test_each_scenario_resolves_expected_category(self):
        scenarios = demo_triage_objects()
        expected = {"dependency": Category.DEPENDENCY,
                    "code": Category.CODE,
                    "config": Category.CONFIG}
        for name, cat in expected.items():
            with self.subTest(scenario=name):
                diag = _agent().investigate(scenarios[name])
                self.assertEqual(diag.category, cat)

    def test_unknown_category_is_inferred_not_left_unknown(self):
      
        triage = demo_triage_objects()["config"]
        self.assertEqual(triage.category, Category.UNKNOWN)
        diag = _agent().investigate(triage)
        self.assertEqual(diag.category, Category.CONFIG)


class PastIncidentTest(unittest.TestCase):
    def test_dependency_matches_memory_and_is_confident(self):
        diag = _agent().investigate(demo_triage_objects()["dependency"])
        self.assertTrue(diag.related_past_incidents)
        self.assertIn("query_past_incidents", diag.tools_used)
       
        self.assertGreaterEqual(diag.confidence, 0.75)
        self.assertFalse(diag.needs_human)


class ToolTest(unittest.TestCase):
    def test_query_past_incidents_matches_on_signature(self):
        r = tools.execute("query_past_incidents",
                          {"error_signature": "connection refused to db"})
        self.assertTrue(r["found"])
        self.assertGreaterEqual(r["match_count"], 1)

    def test_unknown_tool_returns_error_not_raise(self):
        r = tools.execute("no_such_tool", {})
        self.assertIn("error", r)

    def test_read_code_miss_is_graceful(self):
        r = tools.execute("read_code", {"file": "/nope.py", "line": 1})
        self.assertFalse(r["found"])

    def test_all_tools_have_valid_anthropic_schema(self):
        for t in tools.all_tools():
            schema = t.to_anthropic_schema()
            self.assertIn("name", schema)
            self.assertIn("description", schema)
            self.assertEqual(schema["input_schema"]["type"], "object")


class ContractTest(unittest.TestCase):
    def test_triage_roundtrip(self):
        t = demo_triage_objects()["code"]
        again = TriageObject.from_dict(t.to_dict())
        self.assertEqual(again.incident_id, t.incident_id)
        self.assertEqual(again.category, t.category)

    def test_diagnosis_roundtrip(self):
        diag = _agent().investigate(demo_triage_objects()["code"])
        d = diag.to_dict()
       
        self.assertIn("confidence_label", d)
        again = Diagnosis.from_dict(d)
        self.assertEqual(again.incident_id, diag.incident_id)
        self.assertEqual(again.category, diag.category)
        self.assertAlmostEqual(again.confidence, diag.confidence, places=6)
        self.assertEqual(len(again.evidence), len(diag.evidence))

    def test_category_coerce_is_forgiving(self):
        self.assertEqual(Category.coerce("DEPENDENCY"), Category.DEPENDENCY)
        self.assertEqual(Category.coerce("nonsense"), Category.UNKNOWN)


class FunctionalApiTest(unittest.TestCase):
    def test_one_call_helper(self):
        diag = investigate(demo_triage_objects()["code"], use_llm=False)
        self.assertIsInstance(diag, Diagnosis)




class _Block:
    """Stand-in for an SDK content block (thinking / text / tool_use)."""
    def __init__(self, type, **kw):
        self.type = type
        self.__dict__.update(kw)


class _Resp:
    def __init__(self, content, stop_reason="tool_use"):
        self.content = content
        self.stop_reason = stop_reason


class _FakeMessages:
    def __init__(self, scripted):
        self._scripted = list(scripted)
        self.calls = 0

    def create(self, **kwargs):
        resp = self._scripted[self.calls]
        self.calls += 1
        return resp


class _FakeClient:
    def __init__(self, scripted):
        self.messages = _FakeMessages(scripted)


class LLMEngineTest(unittest.TestCase):
    def _install_fake_anthropic(self, scripted):
        import types
        fake = types.ModuleType("anthropic")
        fake.Anthropic = lambda *a, **k: _FakeClient(scripted)
        sys.modules["anthropic"] = fake

    def test_llm_loop_dispatches_tools_and_finalizes(self):
       
        scripted = [
            _Resp([_Block("thinking", thinking="checking memory first"),
                   _Block("tool_use", name="query_past_incidents",
                          id="t1", input={"error_signature": "connection refused"})]),
            _Resp([_Block("tool_use", name="search_logs",
                          id="t2", input={"pattern": "connection refused",
                                          "job_id": "checkout-nightly"})]),
            _Resp([_Block("text", text="Root cause is clear."),
                   _Block("tool_use", name="submit_diagnosis", id="t3", input={
                       "root_cause": "orders-db was down",
                       "category": "dependency",
                       "recommended_fix": "wait for failover and re-run",
                       "confidence": 0.9,
                       "summary": "orders-db outage",
                   })]),
        ]
        self._install_fake_anthropic(scripted)
        try:
            agent = Investigator(InvestigatorConfig(use_llm=True, api_key="fake-key"))
            diag = agent.investigate(demo_triage_objects()["dependency"])
        finally:
            sys.modules.pop("anthropic", None)

        self.assertEqual(diag.model, "claude-opus-4-8")
        self.assertEqual(diag.category, Category.DEPENDENCY)
        self.assertIn("query_past_incidents", diag.tools_used)
        self.assertIn("search_logs", diag.tools_used)
        
        self.assertGreater(diag.confidence, 0.5)
        self.assertLessEqual(diag.confidence, 0.98)
        
        self.assertTrue(any("checking memory" in s for s in diag.reasoning_steps))

    def test_llm_hitting_iteration_cap_still_returns_diagnosis(self):
       
        loop = _Resp([_Block("tool_use", name="query_past_incidents",
                             id="t", input={"error_signature": "connection refused"})])
        self._install_fake_anthropic([loop] * 10)
        try:
            agent = Investigator(InvestigatorConfig(use_llm=True, api_key="fake-key",
                                                    max_iterations=3))
            diag = agent.investigate(demo_triage_objects()["dependency"])
        finally:
            sys.modules.pop("anthropic", None)

        self.assertIsInstance(diag, Diagnosis)
        self.assertTrue(diag.root_cause)  
        self.assertTrue(any("max_iterations" in s for s in diag.reasoning_steps))


if __name__ == "__main__":
    unittest.main(verbosity=2)