"""Protect valid JSONL records when repairing interrupted checkpoint writes."""

import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path

from experiment import analyze, harness


class TestCheckpoints(unittest.TestCase):
    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = Path(directory.name) / "chains.jsonl"

    def test_unicode_separators_are_content_for_both_readers(self):
        for separator in ("\u0085", "\u2028", "\u2029"):
            records = [
                {"key": key, "answer": f"before{separator}after"}
                for key in ("first", "last")
            ]
            data = "".join(
                json.dumps(r, ensure_ascii=False) + "\n" for r in records
            ).encode()
            for reader in (harness.load_chains, analyze.load_records):
                with self.subTest(separator=repr(separator), reader=reader.__name__):
                    self.path.write_bytes(data)
                    actual = reader(self.path)
                    if isinstance(actual, dict):
                        actual = list(actual.values())
                    self.assertEqual(actual, records)
                    self.assertEqual(self.path.read_bytes(), data)

    def test_complete_record_without_newline_is_repaired_once(self):
        record = {"key": "complete", "answer": "before\u2028after"}
        data = json.dumps(record, ensure_ascii=False).encode()
        self.path.write_bytes(data)
        self.assertEqual(harness.load_chains(self.path), {"complete": record})
        self.assertEqual(self.path.read_bytes(), data + b"\n")
        harness.load_chains(self.path)
        self.assertEqual(self.path.read_bytes(), data + b"\n")

    def test_torn_tail_after_unicode_record_preserves_complete_bytes(self):
        record = {"key": "complete", "answer": "before\u2029after"}
        complete = (json.dumps(record, ensure_ascii=False) + "\n").encode()
        original = complete + b'{"key": "unfinished'
        self.path.write_bytes(original)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(analyze.load_records(self.path), [record])
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(harness.load_chains(self.path), {"complete": record})
        self.assertEqual(self.path.read_bytes(), complete)

    def test_incomplete_utf8_at_end_is_ignored_or_repaired(self):
        record = {"key": "complete", "answer": "Zmierzyłem"}
        complete = (json.dumps(record, ensure_ascii=False) + "\n").encode()
        original = complete + b'{"key": "unfinished", "answer": "\xc5'
        self.path.write_bytes(original)
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(analyze.load_records(self.path), [record])
            self.assertEqual(self.path.read_bytes(), original)
            self.assertEqual(harness.load_chains(self.path), {"complete": record})
        self.assertEqual(self.path.read_bytes(), complete)

    def test_invalid_utf8_in_middle_raises_without_rewriting(self):
        original = b'{"key": "broken", "answer": "\xc5\n{"key": "complete"}\n'
        for reader in (harness.load_chains, analyze.load_records):
            with self.subTest(reader=reader.__name__):
                self.path.write_bytes(original)
                with self.assertRaises(UnicodeDecodeError):
                    reader(self.path)
                self.assertEqual(self.path.read_bytes(), original)
