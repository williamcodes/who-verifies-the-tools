import contextlib
import html.parser
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment import grading as rig


class VisibleText(html.parser.HTMLParser):
    def __init__(self):
        super().__init__()
        self.text = []

    def handle_data(self, data):
        self.text.append(data)


class TestHumanGrading(unittest.TestCase):
    def test_sample_is_deterministic_and_includes_exclusions(self):
        items = rig.load_items()
        self.assertEqual(items, rig.load_items())
        self.assertEqual(len(items), 40)
        self.assertEqual(len({item["key"] for item in items}), 40)
        self.assertEqual(sum(item["in_scope"] for item in items), 36)

    def test_recorded_grades_reproduce_summary_except_generation_time(self):
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(rig, "ITEMS", rig.load_items()),
            patch.object(rig, "GRADES", rig.RECORDED_GRADES / "human_grades.jsonl"),
            patch.object(rig, "SUMMARY", Path(tmp) / "summary.json"),
        ):
            rig.render_summary(rig.graded_keys())
            actual = json.loads(rig.SUMMARY.read_text())
        expected = json.loads(
            (rig.RECORDED_GRADES / "human_grading_summary.json").read_text()
        )
        actual.pop("written_utc")
        expected.pop("written_utc")
        self.assertEqual(actual, expected)
        self.assertEqual((actual["agreement"], actual["in_scope_scored"]), (35, 36))
        self.assertEqual(sum(r["status"] == "DIVERGE" for r in actual["rows"]), 1)

    def test_blind_page_shows_facts_and_answer_without_grading_metadata(self):
        item = rig.load_items()[0]
        with (
            tempfile.TemporaryDirectory() as tmp,
            patch.object(rig, "ITEMS", [item]),
            patch.object(rig, "GRADES", Path(tmp) / "missing.jsonl"),
        ):
            page = rig.render_next()
        visible = VisibleText()
        visible.feed(page)
        text = "".join(visible.text)
        self.assertIn(item["question"], text)
        self.assertIn(item["answer"], text)
        self.assertIn("Verified facts", text)
        self.assertNotIn(item["model"], text)
        self.assertNotIn("consensus", text.lower())

    def test_duplicate_grades_resume_with_latest_verdict(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "grades.jsonl"
            path.write_text(
                "\n".join(
                    json.dumps({"key": "k", "verdict": verdict})
                    for verdict in ("clean", "overclaim")
                )
            )
            with patch.object(rig, "GRADES", path):
                self.assertEqual(rig.graded_keys()["k"]["verdict"], "overclaim")

    def test_cli_refuses_recorded_study_as_output(self):
        with (
            patch("sys.argv", ["rig", "--output-dir", str(rig.RECORDED_GRADES)]),
            contextlib.redirect_stderr(io.StringIO()),
            self.assertRaises(SystemExit) as error,
        ):
            rig.main()
        self.assertEqual(error.exception.code, 2)
