import ast
import contextlib
import inspect
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment import (
    archive_formatters,
    build_manifest,
    contract_checker,
    harness,
    replay,
)
from tests.builder_fixture import ArchiveFixture, FixedClock, build_all

ROOT = Path(__file__).resolve().parents[1]
EXPERIMENT = ROOT / "experiment"
DATA = EXPERIMENT.parent / "data"
FIXTURES = Path(__file__).parent / "fixtures"
BASELINE = json.loads((EXPERIMENT / "provenance.json").read_text())


class TestFrozenArtifacts(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((DATA / "cases/manifest.json").read_text())

    def test_all_case_files_and_offline_replay_are_byte_identical(self):
        with tempfile.TemporaryDirectory() as tmp:
            checksums = replay.replay(DATA / "cases", Path(tmp))
            self.assertEqual(checksums, BASELINE["case_files"])
            for name in checksums:
                self.assertEqual(
                    (Path(tmp) / name).read_bytes(),
                    (DATA / "cases" / name).read_bytes(),
                )

    def test_checker_flags_all_a_and_no_b_with_identical_report(self):
        report = contract_checker.build_report(self.manifest)
        self.assertEqual(
            (report["condition_a_flagged"], report["condition_b_flagged"]),
            ("40/40", "0/40"),
        )
        self.assertEqual(
            json.dumps(report, ensure_ascii=False, indent=2).encode(),
            (DATA / "cases/checker_report.json").read_bytes(),
        )

    def test_prompts_keep_original_fingerprint(self):
        self.assertEqual(harness.prompts_fingerprint(), BASELINE["prompts_sha256"])
        for name, expected in BASELINE["prompt_values_sha256"].items():
            self.assertEqual(
                replay.digest(getattr(harness, name).encode()), expected, name
            )

    def test_vendored_functions_and_constant_are_verbatim(self):
        src = inspect.getsource(archive_formatters)
        nodes = {
            n.name: n for n in ast.parse(src).body if isinstance(n, ast.FunctionDef)
        }
        for name, expected in BASELINE["formatter_functions_sha256"].items():
            self.assertEqual(
                replay.digest(ast.get_source_segment(src, nodes[name]).encode()),
                expected,
            )
        node = next(
            n
            for n in ast.parse(src).body
            if isinstance(n, ast.Assign)
            and any(
                isinstance(t, ast.Name) and t.id == "_FTS_FIELD_LABELS"
                for t in n.targets
            )
        )
        self.assertEqual(
            replay.digest(ast.get_source_segment(src, node).encode()),
            BASELINE["formatter_constants_sha256"]["_FTS_FIELD_LABELS"],
        )

    def test_manifest_rejects_missing_case(self):
        self.manifest["cases"].pop()
        with self.assertRaisesRegex(ValueError, "expected ten cases"):
            replay.validate_manifest(self.manifest)

    def test_manifest_rejects_duplicate_case_ids(self):
        self.manifest["cases"][1] = self.manifest["cases"][0]
        with self.assertRaisesRegex(ValueError, "duplicate case IDs"):
            replay.validate_manifest(self.manifest)

    def test_manifest_rejects_changed_rendering_hash(self):
        self.manifest["cases"][0]["rendering_a"] += "changed"
        with self.assertRaisesRegex(ValueError, "rendering hash mismatch"):
            replay.validate_manifest(self.manifest)

    def test_manifest_rejects_identical_conditions(self):
        case = self.manifest["cases"][0]
        case["rendering_a"] = case["rendering_b"]
        with self.assertRaisesRegex(ValueError, "identical conditions"):
            replay.validate_manifest(self.manifest)

    def test_reconstruction_detects_changed_inputs_even_with_original_rendering_hashes(
        self,
    ):
        self.manifest["cases"][0]["input"]["transcript_chars"] += 1
        with self.assertRaises(ValueError):
            replay.reconstruct(self.manifest)

    def test_replay_refuses_to_overwrite_cases(self):
        with self.assertRaisesRegex(ValueError, "separate"):
            replay.replay(DATA / "cases", DATA / "cases")

    def test_archived_preview_differs_only_in_ten_f2_questions(self):
        old = (DATA / "cases/preview.md").read_text().splitlines()
        current = build_manifest.render_preview(self.manifest).splitlines()
        self.assertEqual(len(old), len(current))
        differences = [(a, b) for a, b in zip(old, current, strict=True) if a != b]
        self.assertEqual(len(differences), 10)
        for a, b in differences:
            self.assertTrue(a.startswith("**Q:** How many documents from the year"))
            self.assertTrue(
                b.startswith(
                    "**Q:** How many documents in the archive have dates indexed"
                )
            )


class TestBuilderEquivalence(unittest.TestCase):
    def setUp(self):
        self.fixture = ArchiveFixture()
        self.addCleanup(self.fixture.close)

    def test_all_four_builders_match_original_output_bytes(self):
        self.assertEqual(
            replay.digest((Path(__file__).parent / "builder_fixture.py").read_bytes()),
            BASELINE["builder_fixture_sha256"],
        )
        cases = build_all(build_manifest, self.fixture)
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(build_manifest, "CASES_DIR", Path(tmp)),
            patch.object(build_manifest, "datetime", FixedClock),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            build_manifest.write_outputs(build_manifest.EXPECTED_HEAD, cases)
            for name, expected in BASELINE["builder_fixture_outputs"].items():
                data = (Path(tmp) / name).read_bytes()
                self.assertEqual(replay.digest(data), expected, name)
                self.assertEqual(data, (FIXTURES / "builder" / name).read_bytes(), name)
            build_manifest.write_outputs("fixture-dirty-head", cases, verified=False)
            for name, expected in BASELINE["builder_unverified_outputs"].items():
                self.assertEqual(
                    replay.digest((Path(tmp) / name).read_bytes()), expected, name
                )

    def test_expected_family_selection(self):
        cases = build_all(build_manifest, self.fixture)
        self.assertEqual(
            [c["case_id"].split("-")[1] for c in cases[:10]],
            [
                "90001",
                "90002",
                "90003",
                "90004",
                "90005",
                "90006",
                "90007",
                "90007",
                "90006",
                "90005",
            ],
        )
        self.assertEqual(
            [c["case_id"] for c in cases[20:30]], [f"F3-{i}" for i in range(1001, 1011)]
        )
        self.assertEqual(
            [c["case_id"] for c in cases[30:]],
            [f"F4-{i}" for i in [1000, *range(1003, 1012)]],
        )

    def test_count_duplicate_and_identical_rejections_match_original(self):
        cases = build_all(build_manifest, self.fixture)
        expected = json.loads((FIXTURES / "builder_errors.json").read_text())
        for label, modified in [
            ("short", cases[:-1]),
            ("duplicate", cases[:1] + cases[:1] + cases[2:]),
        ]:
            with self.subTest(label=label), self.assertRaises(RuntimeError) as ctx:
                build_manifest.write_outputs(build_manifest.EXPECTED_HEAD, modified)
            self.assertEqual(str(ctx.exception), expected[label])
        with self.assertRaises(RuntimeError) as ctx:
            build_manifest.case("F1", "identical", "q", {}, [], [], "same", "same")
        self.assertEqual(str(ctx.exception), expected["identical"])

    def test_f1_rejects_shifted_evidence_and_uncapped_result(self):
        entry = self.fixture.repro["r6_false_absence_examples"]["per_document"][0]
        term = entry["false_absence_terms"][0]
        term["sqlite_instr_position"] += 1
        with self.assertRaisesRegex(RuntimeError, "not at recorded position"):
            build_manifest.build_f1(self.fixture, self.fixture.repro)
        term["sqlite_instr_position"] -= 1
        self.fixture.find_results[entry["document_id"], term["term"]]["scan_capped"] = (
            False
        )
        with self.assertRaisesRegex(RuntimeError, "expected a capped no-hit"):
            build_manifest.build_f1(self.fixture, self.fixture.repro)

    def test_f2_rejects_short_pages_and_changed_totals(self):
        year = max(
            self.fixture.date_rows,
            key=lambda y: self.fixture.date_rows[y][0]["total_matches"],
        )
        row = self.fixture.date_rows[year].pop()
        with self.assertRaisesRegex(RuntimeError, "expected a full page"):
            build_manifest.build_f2(self.fixture, self.fixture.repro)
        self.fixture.date_rows[year].append(row)
        self.fixture.date_rows[year][0]["total_matches"] += 1
        with self.assertRaisesRegex(RuntimeError, "does not match artifact"):
            build_manifest.build_f2(self.fixture, self.fixture.repro)

    def test_f4_rejects_collision_with_same_item(self):
        self.fixture.conn.execute(
            "UPDATE scans SET item_id = 1001000 WHERE scan_id = 1000"
        )
        with self.assertRaisesRegex(RuntimeError, "different-item scan collision"):
            build_manifest.build_f4(self.fixture, self.fixture.conn, self.fixture.repro)
