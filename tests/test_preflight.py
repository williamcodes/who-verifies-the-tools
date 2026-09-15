import contextlib
import io
import sqlite3
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment import build_manifest as builder


class TestHistoricalPreflight(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        self.database = self.root / "archive.db"
        with sqlite3.connect(self.database) as conn:
            conn.execute("CREATE TABLE schema_version (version INTEGER)")
            conn.execute("INSERT INTO schema_version VALUES (1)")
        self.config = types.SimpleNamespace(
            config={"database": {"path": str(self.database)}}
        )
        migrations = types.ModuleType("migrations")
        migrations.MIGRATIONS = ["fixture"]
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        self.stack.enter_context(patch.object(builder, "SRC_REPO", self.root))
        self.stack.enter_context(patch.dict("sys.modules", {"migrations": migrations}))

    def git(self, head=None, dirty=""):
        return patch.object(
            builder.subprocess,
            "run",
            side_effect=[
                types.SimpleNamespace(stdout=head or builder.EXPECTED_HEAD),
                types.SimpleNamespace(stdout=dirty),
            ],
        )

    def test_expected_state_opens_database_read_only(self):
        before = self.database.read_bytes()
        with (
            self.git(),
            patch.object(sqlite3, "connect", wraps=sqlite3.connect) as connect,
        ):
            self.assertEqual(
                builder.preflight(self.config), (builder.EXPECTED_HEAD, True)
            )
        self.assertEqual(
            connect.call_args.args, (f"file:{self.database.resolve()}?mode=ro",)
        )
        self.assertEqual(connect.call_args.kwargs, {"uri": True})
        self.assertEqual(self.database.read_bytes(), before)

    def test_wrong_head_and_dirty_source_are_rejected(self):
        with (
            self.git(head="wrong"),
            self.assertRaisesRegex(SystemExit, "source repo HEAD"),
        ):
            builder.preflight(self.config)
        with (
            self.git(dirty=" M rag.py"),
            self.assertRaisesRegex(SystemExit, "uncommitted changes"),
        ):
            builder.preflight(self.config)

    def test_allow_dirty_marks_output_unverified(self):
        with (
            self.git(head="wrong", dirty=" M rag.py"),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            self.assertEqual(
                builder.preflight(self.config, allow_dirty=True), ("wrong", False)
            )

    def test_migration_mismatch_is_not_downgraded_by_allow_dirty(self):
        with sqlite3.connect(self.database) as conn:
            conn.execute("UPDATE schema_version SET version=0")
        before = self.database.read_bytes()
        with self.git(), self.assertRaisesRegex(SystemExit, "would migrate"):
            builder.preflight(self.config, allow_dirty=True)
        self.assertEqual(self.database.read_bytes(), before)

    def test_unexpected_database_path_is_rejected(self):
        self.config.config["database"]["path"] = str(self.root / "different.db")
        with self.git(), self.assertRaisesRegex(SystemExit, "expected"):
            builder.preflight(self.config)
