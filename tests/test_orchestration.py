"""Exercise the CLI orchestration and resume logic using a scripted transport."""

import contextlib
import io
import json
import tempfile
import threading
import unittest
from pathlib import Path
from unittest.mock import patch

from experiment import harness


class ScriptedClient:
    calls = []

    def __init__(self, key, log_path):
        # Match the transport lifetime: the harness closes the client.
        self.log_file = open(log_path, "a")  # noqa: SIM115

    def close(self):
        self.log_file.close()

    def log(self, kind, record):
        self.log_file.write(json.dumps({"kind": kind, **record}) + "\n")

    def call(
        self,
        model,
        system_prompt,
        user_prompt,
        temperature,
        max_tokens=1000,
        context=None,
    ):
        self.calls.append(context)
        if system_prompt in (harness.JUDGE_SYSTEM, harness.META_SYSTEM):
            result = {"refusal": False, "asserted": [False, False], "quotes": ["", ""]}
        elif system_prompt == harness.AGENT_SYSTEM:
            return {"content": "The searched portion does not contain the word."}
        else:
            result = {"verdict": "UNSUPPORTED", "reason": "fixture"}
        return {"content": json.dumps(result)}


class TestOrchestration(unittest.TestCase):
    def setUp(self):
        ScriptedClient.calls = []
        harness.ABORT.clear()
        self.addCleanup(harness.ABORT.clear)
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        root = Path(self.tmp.name)
        self.runs = root / "runs"
        self.manifest = root / "manifest.json"
        case = {
            "case_id": "F1-1-test",
            "family": "F1",
            "question": 'Does the word "example" appear?',
            "facts": {"position": 123},
            "allowed_claims": ["not found in the searched portion"],
            "forbidden_claims": [
                "asserts absence from the document",
                "asserts the full text was searched",
            ],
            "rendering_a": "No occurrence. Searched the FULL text.",
            "rendering_b": "No occurrence in the first 1,000,000 characters.",
        }
        self.manifest.write_text(json.dumps({"built_utc": "fixture", "cases": [case]}))
        self.stack = contextlib.ExitStack()
        self.addCleanup(self.stack.close)
        for name, value in (
            ("MANIFEST", self.manifest),
            ("RUNS", self.runs),
            ("POOL_WORKERS", 1),
            ("OpenRouterClient", ScriptedClient),
            ("read_api_key", lambda: "fixture-key"),
            ("account_credits", lambda key: 100.0),
        ):
            self.stack.enter_context(patch.object(harness, name, value))

    def run_mode(self, mode, *extra):
        with (
            patch("sys.argv", ["harness", "--mode", mode, *extra]),
            contextlib.redirect_stdout(io.StringIO()),
        ):
            harness.main()

    def test_smoke_writes_complete_checkpoints_and_resume_skips_them(self):
        self.run_mode("smoke")
        run = next(self.runs.iterdir())
        records = [
            json.loads(line) for line in (run / "chains.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(records), 2)
        self.assertEqual({r["cond"] for r in records}, {"a", "b"})
        for name in ("meta.json", "summary.json", "transcripts.md"):
            self.assertTrue((run / name).is_file())
        self.assertFalse((run / "run.lock").exists())
        calls = len(ScriptedClient.calls)
        self.run_mode("smoke", "--resume", run.name)
        self.assertEqual(len(ScriptedClient.calls), calls)
        self.assertEqual(len((run / "chains.jsonl").read_text().splitlines()), 2)

    def test_fixed_arm_writes_six_verdicts_and_resume_skips_them(self):
        self.run_mode("pilot-fixed")
        run = next(self.runs.iterdir())
        records = [
            json.loads(line) for line in (run / "chains.jsonl").read_text().splitlines()
        ]
        self.assertEqual(len(records), 6)
        self.assertTrue(all(r["verdict_status"] == "ok" for r in records))
        self.assertFalse((run / "run.lock").exists())
        self.run_mode("pilot-fixed", "--resume", run.name)
        self.assertEqual(len(ScriptedClient.calls), 6)

    def test_pilot_execution_order_matches_frozen_seed(self):
        self.run_mode("pilot")
        expected = [
            ("a", "stealth/ox-alpha", 0),
            ("a", "openai/gpt-5.6-sol", 0),
            ("a", "google/gemini-3.1-pro-preview", 0),
            ("b", "openai/gpt-5.6-sol", 0),
            ("a", "anthropic/claude-sonnet-5", 0),
            ("b", "google/gemini-3.1-pro-preview", 0),
            ("b", "anthropic/claude-sonnet-5", 0),
            ("b", "stealth/ox-alpha", 0),
        ]
        actual = [
            (call["cond"], call["agent_model"], call["rep"])
            for call in ScriptedClient.calls
            if call["role"] == "agent"
        ]
        self.assertEqual(actual, expected)

    def test_pilot_fixed_execution_order_matches_frozen_seed(self):
        self.run_mode("pilot-fixed")
        expected = [
            ("a", "google/gemini-3.1-pro-preview", 0),
            ("a", "openai/gpt-5.6-sol", 0),
            ("b", "google/gemini-3.1-pro-preview", 0),
            ("a", "anthropic/claude-sonnet-5", 0),
            ("b", "openai/gpt-5.6-sol", 0),
            ("b", "anthropic/claude-sonnet-5", 0),
        ]
        actual = [
            (call["cond"], call["verifier_model"], call["rep"])
            for call in ScriptedClient.calls
            if call["role"] == "verifier_fixed"
        ]
        self.assertEqual(actual, expected)

    def test_resume_rejects_changed_manifest_before_more_calls(self):
        self.run_mode("smoke")
        run = next(self.runs.iterdir())
        self.manifest.write_text(self.manifest.read_text() + "\n")
        calls = len(ScriptedClient.calls)
        with self.assertRaisesRegex(SystemExit, "manifest_sha256"):
            self.run_mode("smoke", "--resume", run.name)
        self.assertEqual(len(ScriptedClient.calls), calls)

    def test_resume_lock_refuses_concurrent_writer(self):
        self.run_mode("smoke")
        run = next(self.runs.iterdir())
        (run / "run.lock").write_text("another process")
        with self.assertRaisesRegex(SystemExit, "another process"):
            self.run_mode("smoke", "--resume", run.name)
        self.assertTrue((run / "run.lock").exists())

    def assert_recoverable_run(self, mode, expected_records):
        """A stopped run keeps completed work and resumes its remaining tasks."""
        run = next(self.runs.iterdir())
        records = harness.load_chains(run / "chains.jsonl")
        self.assertEqual(len(records), 1)
        completed_key = next(iter(records))
        self.assertFalse((run / "run.lock").exists())
        meta = json.loads((run / "meta.json").read_text())
        self.assertIn("finished", meta["sessions"][-1])
        self.assertEqual(meta["sessions"][-1]["credits_after"], 100.0)
        summary = json.loads((run / "summary.json").read_text())
        if mode == "smoke":
            self.assertEqual(summary["chains_completed"], 1)
            self.assertTrue((run / "transcripts.md").is_file())
        else:
            self.assertEqual(len(summary["records"]), 1)

        # A fresh process would start with an unset abort flag.
        harness.ABORT.clear()
        ScriptedClient.calls.clear()
        self.run_mode(mode, "--resume", run.name)
        resumed = harness.load_chains(run / "chains.jsonl")
        self.assertEqual(len(resumed), expected_records)
        self.assertEqual(resumed[completed_key], records[completed_key])
        self.assertEqual(
            len((run / "chains.jsonl").read_text().splitlines()), expected_records
        )
        self.assertFalse((run / "run.lock").exists())

    def assert_worker_failure_recovers(self, mode, function_name, expected_records):
        run_task = getattr(harness, function_name)
        started = 0

        def fail_after_first(*args, **kwargs):
            nonlocal started
            started += 1
            if started == 1:
                return run_task(*args, **kwargs)
            raise RuntimeError("fixture worker failed")

        # Consume real worker futures in submission order so the test always
        # observes one completed checkpoint before the injected failure.
        with (
            patch.object(harness, function_name, side_effect=fail_after_first),
            patch.object(harness, "as_completed", side_effect=iter),
            self.assertRaisesRegex(RuntimeError, "fixture worker failed"),
        ):
            self.run_mode(mode)
        self.assertTrue(harness.ABORT.is_set())
        self.assert_recoverable_run(mode, expected_records)

    def test_agent_worker_failure_preserves_checkpoint_and_propagates(self):
        self.assert_worker_failure_recovers("smoke", "run_chain", 2)

    def test_fixed_worker_failure_preserves_checkpoint_and_propagates(self):
        self.assert_worker_failure_recovers("pilot-fixed", "run_fixed_verifier", 6)

    def assert_interruption_recovers(self, mode, function_name, expected_records):
        run_task = getattr(harness, function_name)
        started = 0
        aborted = []
        waiting_for_abort = threading.Event()

        def finish_first_then_wait_for_abort(*args, **kwargs):
            nonlocal started
            started += 1
            if started == 1:
                return run_task(*args, **kwargs)
            waiting_for_abort.set()
            if not harness.ABORT.wait(timeout=2):
                raise AssertionError("interrupted harness did not stop its workers")
            aborted.append(True)
            if mode == "smoke":
                return {"error": "aborted"}
            return {"verdict_status": "aborted"}

        def interrupt_after_first(futures):
            yield futures[0]
            self.assertTrue(waiting_for_abort.wait(timeout=2))
            raise KeyboardInterrupt()

        with (
            patch.object(
                harness, function_name, side_effect=finish_first_then_wait_for_abort
            ),
            patch.object(harness, "as_completed", side_effect=interrupt_after_first),
        ):
            self.run_mode(mode)
        self.assertTrue(harness.ABORT.is_set())
        # At least one task was running during shutdown and returned the abort
        # sentinel; it must not become a completed checkpoint.
        self.assertTrue(aborted)
        self.assert_recoverable_run(mode, expected_records)

    def test_agent_interruption_skips_aborted_records_and_allows_resume(self):
        self.assert_interruption_recovers("smoke", "run_chain", 2)

    def test_fixed_interruption_skips_aborted_records_and_allows_resume(self):
        self.assert_interruption_recovers("pilot-fixed", "run_fixed_verifier", 6)

    def test_credit_guard_rejects_run_and_releases_lock(self):
        for mode in ("pilot", "pilot-fixed"):
            with (
                self.subTest(mode=mode),
                patch.object(harness, "RUNS", self.runs / mode),
                patch.object(harness, "account_credits", return_value=0.0),
            ):
                with self.assertRaisesRegex(SystemExit, "credits check failed"):
                    self.run_mode(mode)
                run = next((self.runs / mode).iterdir())
                self.assertFalse((run / "run.lock").exists())
                self.assertFalse((run / "chains.jsonl").exists())
                self.assertEqual(ScriptedClient.calls, [])

    def test_pool_startup_failure_closes_client_and_releases_lock(self):
        for mode in ("smoke", "pilot-fixed"):
            with (
                self.subTest(mode=mode),
                patch.object(harness, "RUNS", self.runs / mode),
                patch.object(
                    harness,
                    "ThreadPoolExecutor",
                    side_effect=RuntimeError("pool failed"),
                ),
                patch.object(
                    ScriptedClient,
                    "close",
                    autospec=True,
                    side_effect=ScriptedClient.close,
                ) as close,
            ):
                with self.assertRaisesRegex(RuntimeError, "pool failed"):
                    self.run_mode(mode)
                close.assert_called_once()
                self.assertTrue(close.call_args.args[0].log_file.closed)
                run = next((self.runs / mode).iterdir())
                self.assertFalse((run / "run.lock").exists())
                self.assertFalse((run / "chains.jsonl").exists())
                self.assertEqual(ScriptedClient.calls, [])
