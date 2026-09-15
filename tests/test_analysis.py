import contextlib
import io
import json
import shutil
import tempfile
import unittest
from pathlib import Path

from experiment import analyze, replay

EXPERIMENT = Path(__file__).resolve().parents[1] / "experiment"
DATA = EXPERIMENT.parent / "data"
BASELINE = json.loads((EXPERIMENT / "provenance.json").read_text())


class TestAnalysis(unittest.TestCase):
    def test_full_and_fixed_reports_and_human_sample_match_original_bytes(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            shutil.copytree(DATA / "cases", root / "cases")
            for run, expected in BASELINE["analysis_outputs"].items():
                out = root / "runs" / run
                out.mkdir(parents=True)
                for name in ("chains.jsonl", "adjudications.json"):
                    source = DATA / "runs" / run / name
                    if source.exists():
                        shutil.copy2(source, out / name)
                with contextlib.redirect_stdout(io.StringIO()):
                    analyze.main(out)
                for name, digest in expected.items():
                    data = (out / name).read_bytes()
                    self.assertEqual(replay.digest(data), digest, f"{run}/{name}")
                    self.assertEqual(data, (DATA / "runs" / run / name).read_bytes())

    def test_missing_grade_requires_adjudication_and_refusal_still_excludes(self):
        record = {"key": "sample", "judge": {"asserted": [True]}, "meta_judge": None}
        self.assertEqual(analyze.resolve(record, {}), ("awaiting_adjudication", None))
        self.assertEqual(analyze.resolve(record, {"sample": False}), ("graded", False))
        record["judge"]["refusal"] = True
        self.assertEqual(analyze.resolve(record, {"sample": False}), ("refusal", None))
        self.assertEqual(
            analyze.resolve({"key": "sample"}, {"sample": True}),
            ("grading_failed", None),
        )

    def test_empty_denominators_and_document_clusters(self):
        self.assertEqual(analyze.rate(None), analyze.rate([0, 0]))
        self.assertEqual(analyze.overclaim_rate([]), (0, 0))
        self.assertIsNone(analyze.bootstrap_diff({}, analyze.BOOTSTRAP_SEED))
        self.assertEqual(
            analyze.cluster_key({"family": "F1", "case": "F1-77-term1"}),
            analyze.cluster_key({"family": "F1", "case": "F1-77-term2"}),
        )
        self.assertEqual(
            analyze.cluster_key({"family": "F3", "case": "F3-77"}), "F3-77"
        )

    def test_holdout_has_32_cases_and_excludes_first_two_per_family(self):
        manifest = json.loads((DATA / "cases/manifest.json").read_text())
        pilot = analyze.pilot_case_ids(manifest)
        self.assertEqual(len(pilot), 8)
        self.assertEqual(
            len([c for c in manifest["cases"] if c["case_id"] not in pilot]), 32
        )
        self.assertFalse(analyze.is_named("stealth/ox-alpha"))
        for family in ("F1", "F2", "F3", "F4"):
            first_two = [
                c["case_id"] for c in manifest["cases"] if c["family"] == family
            ][:2]
            self.assertTrue(set(first_two).issubset(pilot))

    def test_named_grading_population_matches_paper(self):
        run = DATA / "runs/20260826T015731Z-full"
        records = [
            r
            for r in analyze.load_records(run / "chains.jsonl")
            if analyze.is_named(r["model"])
        ]
        dual = [
            (
                analyze.grader_overclaim(r.get("judge")),
                analyze.grader_overclaim(r.get("meta_judge")),
            )
            for r in records
        ]
        dual = [(a, b) for a, b in dual if a is not None and b is not None]
        self.assertEqual(len(records), 1200)
        self.assertEqual(len(dual), 1199)
        self.assertEqual(sum(a == b for a, b in dual), 1147)

    def test_fixed_answer_arm_requires_paired_verdicts_for_flips(self):
        rows = [
            {
                "kind": "verifier_fixed",
                "case": "F1-1",
                "family": "F1",
                "model": "v",
                "cond": cond,
                "verdict": {"verdict": verdict},
            }
            for cond, verdict in [("a", "SUPPORTED"), ("b", "UNSUPPORTED")]
        ]
        text = "\n".join(analyze.analyze_fixed_arm(rows, []))
        self.assertIn("1/1 (100%)", text)
        self.assertIn("0/1 (0%)", text)
