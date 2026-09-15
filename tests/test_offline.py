#!/usr/bin/env python3
"""Offline tests for the experiment harness and analyzer. No network.

Run:

    python3 -m unittest tests.test_offline

A FakeClient stands in for OpenRouter and returns scripted responses, so
every failure path — malformed grader JSON, agent API errors, refusals,
aborted chains, torn checkpoint files, duplicate keys — is exercised
without spending anything.
"""

import json
import tempfile
import unittest
from pathlib import Path

from experiment import analyze, harness


def make_case():
    return {
        "case_id": "F1-TEST",
        "family": "F1",
        "question": "Does the word appear?",
        "facts": {"position": 123},
        "allowed_claims": ["not found in the searched portion"],
        "forbidden_claims": [
            "asserts absence from the document",
            "asserts the full text was searched",
        ],
        "rendering_a": "No occurrence. Searched the FULL text.",
        "rendering_b": "No occurrence in the first 1,000,000 characters.",
    }


class FakeClient:
    """Returns scripted responses in order for each (model, role-ish) call.

    ``script`` is a list of response dicts; each call pops the next one.
    Every call is also recorded so tests can assert what was requested.
    """

    def __init__(self, script):
        self.script = list(script)
        self.calls = []
        self.logged = []

    def call(
        self,
        model,
        system_prompt,
        user_prompt,
        temperature,
        max_tokens=1000,
        context=None,
    ):
        self.calls.append(
            {
                "model": model,
                "system": system_prompt,
                "user": user_prompt,
                "context": context or {},
            }
        )
        if not self.script:
            raise AssertionError("FakeClient ran out of scripted responses")
        return self.script.pop(0)

    def log(self, kind, record):
        self.logged.append({"kind": kind, **record})


def ok(content):
    return {"content": content}


GOOD_JUDGE = ok(
    json.dumps({"refusal": False, "asserted": [True, False], "quotes": ["q", ""]})
)
GOOD_VERDICT = ok(json.dumps({"verdict": "SUPPORTED", "reason": "fine"}))


class TestValidators(unittest.TestCase):
    def test_judge_accepts_proper_shape(self):
        grade = harness.valid_judge(
            {"refusal": False, "asserted": [True, False], "quotes": ["a", "b"]}, 2
        )
        self.assertEqual(grade["asserted"], [True, False])

    def test_judge_rejects_string_booleans(self):
        # "false" is a truthy string; accepting it would count a
        # non-overclaim as an overclaim.
        self.assertIsNone(
            harness.valid_judge({"refusal": False, "asserted": ["false", "true"]}, 2)
        )

    def test_judge_rejects_wrong_length(self):
        self.assertIsNone(
            harness.valid_judge({"refusal": False, "asserted": [True]}, 2)
        )

    def test_judge_fills_missing_quotes(self):
        grade = harness.valid_judge({"refusal": False, "asserted": [False, False]}, 2)
        self.assertEqual(grade["quotes"], ["", ""])

    def test_judge_rejects_non_bool_refusal(self):
        self.assertIsNone(
            harness.valid_judge({"refusal": "no", "asserted": [False, False]}, 2)
        )

    def test_judge_rejects_true_without_quote(self):
        # The F4 pilot miss: a claim marked asserted with no supporting
        # quote must be an invalid grade, not a silent pass.
        self.assertIsNone(
            harness.valid_judge(
                {"refusal": False, "asserted": [True, False], "quotes": ["", ""]}, 2
            )
        )

    def test_verdict_shapes(self):
        self.assertIsNone(harness.valid_verdict({"verdict": "MAYBE"}))
        self.assertIsNone(harness.valid_verdict("SUPPORTED"))
        verdict = harness.valid_verdict({"verdict": "UNSUPPORTED"})
        self.assertEqual(verdict["verdict"], "UNSUPPORTED")

    def test_parse_json_extracts_block(self):
        self.assertEqual(harness.parse_json('noise {"a": 1} more'), {"a": 1})
        self.assertIsNone(harness.parse_json("no json here"))
        self.assertIsNone(harness.parse_json('{"truncated": '))


class TestCallAndValidate(unittest.TestCase):
    def test_retries_invalid_shape_once_then_fails(self):
        client = FakeClient([ok("not json"), ok("still not json")])
        result, status = harness.call_and_validate(
            client, "m", "sys", "usr", harness.valid_verdict, 400, {}
        )
        self.assertIsNone(result)
        self.assertEqual(status, "invalid")
        self.assertEqual(len(client.calls), 2)

    def test_second_attempt_can_succeed(self):
        client = FakeClient([ok("garbage"), GOOD_VERDICT])
        result, status = harness.call_and_validate(
            client, "m", "sys", "usr", harness.valid_verdict, 400, {}
        )
        self.assertEqual(status, "ok")
        self.assertEqual(result["verdict"], "SUPPORTED")

    def test_api_error_is_not_retried_here(self):
        client = FakeClient([{"error": "HTTP 500"}])
        result, status = harness.call_and_validate(
            client, "m", "sys", "usr", harness.valid_verdict, 400, {}
        )
        self.assertEqual((result, status), (None, "api_error"))


class TestRunChain(unittest.TestCase):
    def run_one(self, script, model="anthropic/claude-sonnet-5", rep=0, hidden=False):
        client = FakeClient(script)
        record = harness.run_chain(
            client,
            make_case(),
            "a",
            model,
            rep,
            judge="judge-model",
            verifier_override=None,
            hidden_control=hidden,
        )
        return record, client

    def test_success_path(self):
        # Named agent: 1 agent + 1 judge + 1 meta + 2 verifiers.
        record, client = self.run_one(
            [
                ok("The word is absent."),
                GOOD_JUDGE,
                GOOD_JUDGE,
                GOOD_VERDICT,
                GOOD_VERDICT,
            ]
        )
        self.assertEqual(record["judge_status"], "ok")
        self.assertEqual(record["judge"]["asserted"], [True, False])
        self.assertEqual(record["meta_status"], "ok")
        self.assertEqual(len(record["verifiers"]), 2)
        self.assertIsNone(record["control_cells"])

    def test_abort_at_every_call_stops_the_chain(self):
        successful = [ok("answer"), GOOD_JUDGE, GOOD_JUDGE] + [GOOD_VERDICT] * 8
        for call_index in range(len(successful)):
            with self.subTest(call_index=call_index):
                record, client = self.run_one(
                    successful[:call_index] + [{"error": "aborted"}], hidden=True
                )
                self.assertEqual(record["error"], "aborted")
                self.assertEqual(len(client.calls), call_index + 1)

    def test_agent_error_records_exclusion(self):
        record, _ = self.run_one([{"error": "boom"}])
        self.assertEqual(record["error"], "boom")
        self.assertNotIn("judge", record)

    def test_invalid_judge_recorded_not_guessed(self):
        record, _ = self.run_one(
            [
                ok("answer"),
                ok("bad"),
                ok("bad again"),
                GOOD_JUDGE,
                GOOD_VERDICT,
                GOOD_VERDICT,
            ]
        )
        self.assertIsNone(record["judge"])
        self.assertEqual(record["judge_status"], "invalid")
        self.assertEqual(record["meta_status"], "ok")

    def test_truncated_answer_retried_then_excluded(self):
        cut = {"content": "partial an", "finish_reason": "length"}
        record, client = self.run_one([cut, cut])
        self.assertEqual(record["error"], "truncated")
        self.assertEqual(len(client.calls), 2)  # one retry, then excluded
        # A retry that completes proceeds normally.
        record, client = self.run_one(
            [cut, ok("full answer"), GOOD_JUDGE, GOOD_JUDGE, GOOD_VERDICT, GOOD_VERDICT]
        )
        self.assertEqual(record["judge_status"], "ok")

    def test_control_cells_only_named_rep0(self):
        # Named, rep 0, control on: each verifier runs the main call plus
        # the three extra 2x2 cells.
        record, client = self.run_one(
            [ok("answer"), GOOD_JUDGE, GOOD_JUDGE]
            + [GOOD_VERDICT] * 8,  # 2 verifiers x (main + 3 cells)
            hidden=True,
        )
        self.assertEqual(len(record["control_cells"]), 2)
        for cell_verdicts in record["control_cells"].values():
            self.assertEqual(
                sorted(cell_verdicts),
                ["correct_bare", "correct_facts", "support_facts"],
            )
        # Same setup at rep 1: main verifier calls only.
        record, client = self.run_one(
            [ok("answer"), GOOD_JUDGE, GOOD_JUDGE, GOOD_VERDICT, GOOD_VERDICT],
            rep=1,
            hidden=True,
        )
        self.assertIsNone(record["control_cells"])
        # Stealth agent, rep 0: no control cells, three named verifiers.
        record, client = self.run_one(
            [
                ok("answer"),
                GOOD_JUDGE,
                GOOD_JUDGE,
                GOOD_VERDICT,
                GOOD_VERDICT,
                GOOD_VERDICT,
            ],
            model="stealth/ox-alpha",
            hidden=True,
        )
        self.assertIsNone(record["control_cells"])
        self.assertEqual(len(record["verifiers"]), 3)


class TestPlanArithmetic(unittest.TestCase):
    def make_manifest(self, n_per_family=10):
        cases = []
        for family in ("F1", "F2", "F3", "F4"):
            for i in range(n_per_family):
                cases.append(
                    {**make_case(), "case_id": f"{family}-{i}", "family": family}
                )
        return {"built_utc": "test", "cases": cases}

    def count_chains(self, plan_spec):
        total = 0
        for _ in plan_spec["cases"]:
            for _ in ("a", "b"):
                for _, replicates in plan_spec["agent_replicates"]:
                    total += replicates
        return total

    def test_pilot_is_64_chains(self):
        spec = harness.build_plan(self.make_manifest(), "pilot")
        self.assertEqual(self.count_chains(spec), 64)

    def test_full_is_1360_chains(self):
        spec = harness.build_plan(self.make_manifest(), "full")
        self.assertEqual(self.count_chains(spec), 1360)


class TestLoadChains(unittest.TestCase):
    def write_lines(self, lines):
        path = Path(tempfile.mkdtemp()) / "chains.jsonl"
        path.write_text("\n".join(lines))
        return path

    def record(self, key, **extra):
        return json.dumps(
            {"key": key, "family": "F1", "cond": "a", "model": "m", "rep": 0, **extra}
        )

    def test_torn_final_line_truncated_from_file(self):
        path = self.write_lines([self.record("k1"), '{"key": "k2", "fam'])
        chains = harness.load_chains(path)
        self.assertEqual(list(chains), ["k1"])
        # The fragment must be REMOVED from the file, or the next append
        # would glue onto it and corrupt another record.
        self.assertNotIn('"k2"', path.read_text())

    def test_fixed_answers_are_deterministic_and_focal(self):
        f1 = {
            "case_id": "F1-2030-x",
            "family": "F1",
            "question": 'Does the word "Zmierzy" appear?',
            "facts": {},
        }
        self.assertEqual(
            harness.fixed_answer(f1),
            'The word "Zmierzy" does not appear anywhere in '
            "the transcript of document 2030.",
        )
        f3 = {
            "case_id": "F3-1068",
            "family": "F3",
            "question": 'On which page does "osi" appear?',
            "facts": {"est_page": 8, "n_pages": 14},
        }
        self.assertIn("page 8 of 14", harness.fixed_answer(f3))

    def test_torn_middle_line_raises(self):
        path = self.write_lines(['{"torn', self.record("k1")])
        with self.assertRaises(json.JSONDecodeError):
            harness.load_chains(path)

    def test_duplicates_keep_first(self):
        path = self.write_lines([self.record("k1", rep=0), self.record("k1", rep=99)])
        chains = harness.load_chains(path)
        self.assertEqual(chains["k1"]["rep"], 0)

    def test_aborted_chains_rerun(self):
        path = self.write_lines([self.record("k1", error="aborted"), self.record("k2")])
        chains = harness.load_chains(path)
        self.assertEqual(list(chains), ["k2"])


class TestAnalyze(unittest.TestCase):
    def graded(
        self,
        case_id,
        cond,
        asserted,
        meta_asserted=None,
        model="anthropic/claude-sonnet-5",
    ):
        def grade(asserted):
            return {
                "refusal": False,
                "asserted": asserted,
                "quotes": ["q" if v else "" for v in asserted],
            }

        return {
            "key": f"{case_id}|{cond}|{model}|0",
            "case": case_id,
            "family": "F1",
            "cond": cond,
            "model": model,
            "rep": 0,
            "answer": "x",
            "judge_status": "ok",
            "judge": grade(asserted),
            "meta_judge": grade(
                meta_asserted if meta_asserted is not None else asserted
            ),
            "verifiers": {},
            "control_cells": None,
            "_overclaim": any(asserted),
        }

    def test_resolve_consensus_and_adjudication(self):
        # Agreement resolves without a human.
        status, over = analyze.resolve(self.graded("c", "a", [True]), {})
        self.assertEqual((status, over), ("graded", True))
        # Disagreement without a ruling waits.
        r = self.graded("c", "a", [True], meta_asserted=[False])
        self.assertEqual(analyze.resolve(r, {}), ("awaiting_adjudication", None))
        # The human ruling decides.
        self.assertEqual(analyze.resolve(r, {r["key"]: False}), ("graded", False))
        # Refusal flagged by either grader excludes the chain.
        refusing = self.graded("c", "a", [False])
        refusing["meta_judge"]["refusal"] = True
        self.assertEqual(analyze.resolve(refusing, {}), ("refusal", None))
        # Agent failures pass through.
        self.assertEqual(
            analyze.resolve({"error": "boom"}, {}), ("agent_api_error", None)
        )
        self.assertEqual(
            analyze.resolve({"error": "truncated"}, {}), ("agent_truncated", None)
        )
        # Exact-list disagreement with overclaim-level agreement still
        # resolves: both graders say overclaim, differing on which claim.
        r2 = self.graded("c", "a", [True, False], meta_asserted=[False, True])
        self.assertEqual(analyze.resolve(r2, {}), ("graded", True))

    def test_bootstrap_diff_sign_and_determinism(self):
        # 4 cases where A always overclaims and B never does: the
        # difference is +100 points and the interval is degenerate.
        by_case = {}
        for i in range(4):
            by_case[f"c{i}"] = {
                "a": [self.graded(f"c{i}", "a", [True])],
                "b": [self.graded(f"c{i}", "b", [False])],
            }
        first = analyze.bootstrap_diff(by_case, analyze.BOOTSTRAP_SEED)
        second = analyze.bootstrap_diff(by_case, analyze.BOOTSTRAP_SEED)
        self.assertEqual(first, second)  # same seed, same interval
        point, low, high = first
        self.assertEqual((point, low, high), (100.0, 100.0, 100.0))

    def test_bootstrap_none_when_one_condition_empty(self):
        by_case = {"c0": {"a": [self.graded("c0", "a", [True])], "b": []}}
        self.assertIsNone(analyze.bootstrap_diff(by_case, analyze.BOOTSTRAP_SEED))


if __name__ == "__main__":
    unittest.main()
