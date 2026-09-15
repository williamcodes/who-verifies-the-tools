"""Compare today's execution plans with the calls in the reported experiments."""

import json
import unittest
from collections import Counter
from pathlib import Path

from experiment import harness

DATA = Path(__file__).resolve().parents[1] / "data"


class TestRecordedRuns(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((DATA / "cases/manifest.json").read_text())

    def records(self, run):
        return [
            json.loads(line)
            for line in (DATA / "runs" / run / "chains.jsonl").read_text().splitlines()
        ]

    def test_full_plan_matches_every_recorded_chain_once(self):
        records = self.records("20260826T015731Z-full")
        plan, _ = harness.pending_agent_tasks(
            harness.build_plan(self.manifest, "full"), {}
        )
        expected = Counter(
            harness.chain_key(case["case_id"], condition, model, replicate)
            for case, condition, model, replicate in plan
        )
        self.assertEqual(len(records), 1360)
        self.assertTrue(all(count == 1 for count in expected.values()))
        self.assertEqual(Counter(record["key"] for record in records), expected)

    def test_fixed_plan_and_answers_match_every_recorded_verdict_once(self):
        records = self.records("20260826T015541Z-verifier-fixed")
        plan = harness.build_fixed_plan(self.manifest, "verifier-fixed")
        expected = Counter(
            f"VF|{case['case_id']}|{condition}|{model}"
            for case, condition, model in plan
        )
        self.assertEqual(len(records), 240)
        self.assertTrue(all(count == 1 for count in expected.values()))
        self.assertEqual(Counter(record["key"] for record in records), expected)
        cases = {case["case_id"]: case for case in self.manifest["cases"]}
        for record in records:
            self.assertEqual(
                record["fixed_answer"],
                harness.fixed_answer(cases[record["case"]]),
                record["key"],
            )
