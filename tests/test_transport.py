import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path
from unittest.mock import patch

from experiment import transport


def response(content="ok"):
    return io.StringIO(
        json.dumps(
            {
                "model": "model-v1",
                "provider": "fixture",
                "choices": [{"message": {"content": content}, "finish_reason": "stop"}],
            }
        )
    )


class TestTransport(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / "calls.jsonl"
        self.client = transport.OpenRouterClient("fixture-key", self.path)
        self.addCleanup(self.client.close)
        transport.ABORT.clear()
        self.addCleanup(transport.ABORT.clear)

    def call(self):
        return self.client.call(
            "named/model", "system", "user", 0, context={"case": "fixture"}
        )

    def test_payload_and_attempt_log_preserve_request_contract(self):
        with patch.object(
            transport.urllib.request, "urlopen", return_value=response()
        ) as request:
            result = self.call()
        payload = json.loads(request.call_args.args[0].data)
        self.assertEqual(
            payload,
            {
                "model": "named/model",
                "temperature": 0,
                "max_tokens": 1000,
                "messages": [
                    {"role": "system", "content": "system"},
                    {"role": "user", "content": "user"},
                ],
            },
        )
        self.assertEqual(result["content"], "ok")
        log = json.loads(self.path.read_text())
        self.assertEqual((log["attempt"], log["case"], log["ok"]), (1, "fixture", True))
        self.assertNotIn("fixture-key", self.path.read_text())

    def test_http_retry_after_is_honored(self):
        error = urllib.error.HTTPError(
            "https://example.org", 429, "limited", {"Retry-After": "2"}, None
        )
        with (
            patch.object(
                transport.urllib.request, "urlopen", side_effect=[error, response()]
            ),
            patch.object(transport.ABORT, "wait") as wait,
        ):
            result = self.call()
        wait.assert_called_once_with(2)
        self.assertEqual(result["attempt"], 2)
        self.assertEqual(len(self.path.read_text().splitlines()), 2)

    def test_empty_content_retries_then_succeeds(self):
        with (
            patch.object(
                transport.urllib.request,
                "urlopen",
                side_effect=[response(" "), response()],
            ),
            patch.object(transport.ABORT, "wait") as wait,
        ):
            result = self.call()
        self.assertEqual(result["attempt"], 2)
        wait.assert_called_once_with(8)

    def test_four_failures_exhaust_retry_budget(self):
        with (
            patch.object(
                transport.urllib.request,
                "urlopen",
                side_effect=OSError("offline fixture"),
            ) as request,
            patch.object(transport.ABORT, "wait") as wait,
        ):
            result = self.call()
        self.assertEqual(result["error"], "offline fixture")
        self.assertEqual(request.call_count, 4)
        self.assertEqual([c.args[0] for c in wait.call_args_list], [8, 16, 24, 32])

    def test_abort_stops_before_network_call(self):
        transport.ABORT.set()
        with patch.object(transport.urllib.request, "urlopen") as request:
            self.assertEqual(self.call()["error"], "aborted")
        request.assert_not_called()

    def test_abort_during_retry_stops_next_attempt(self):
        with (
            patch.object(
                transport.urllib.request, "urlopen", side_effect=OSError("fixture")
            ) as request,
            patch.object(
                transport.ABORT, "wait", side_effect=lambda _: transport.ABORT.set()
            ),
        ):
            result = self.call()
        self.assertEqual(result["error"], "aborted")
        self.assertEqual(request.call_count, 1)

    def test_credit_lookup_failure_returns_none(self):
        with patch.object(
            transport.urllib.request, "urlopen", side_effect=OSError("fixture")
        ):
            self.assertIsNone(transport.account_credits("fixture-key"))
