"""OpenRouter transport, retry policy, concurrency limits, and attempt logs."""

import json
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Required, TypedDict

REPO = Path(__file__).resolve().parents[1]
API = "https://openrouter.ai/api/v1"
PER_MODEL_CONCURRENCY = {"stealth/ox-alpha": 1}
DEFAULT_MODEL_CONCURRENCY = 4
ABORT = threading.Event()


class CallResult(TypedDict, total=False):
    """A completed chat request or a failed request with an error message."""

    model_requested: Required[str]
    content: str
    error: str
    finish_reason: str | None
    model_served: str | None
    provider: str | None
    usage: dict[str, Any] | None
    latency_s: float
    attempt: int


def read_api_key() -> str:
    for line in (REPO / ".env").read_text().splitlines():
        if line.startswith("OPENROUTER_API_KEY="):
            return line.split("=", 1)[1].strip()
    sys.exit("OPENROUTER_API_KEY not found in .env")


class OpenRouterClient:
    """Sends chat requests and logs every attempt to calls.jsonl.

    Because many worker threads share one client, the two shared things are
    protected: the log file by a lock (so lines don't interleave), and each
    model by a semaphore (so at most N requests are in flight to it).
    """

    def __init__(self, key: str, log_path: str | Path) -> None:
        self.key = key
        # Shared across calls; run_tasks owns this client and calls close().
        self.log_file = open(log_path, "a")  # noqa: SIM115
        self.log_lock = threading.Lock()
        self.semaphores = {}
        self.semaphores_lock = threading.Lock()

    def close(self) -> None:
        self.log_file.close()

    def _semaphore_for(self, model: str) -> threading.Semaphore:
        with self.semaphores_lock:
            if model not in self.semaphores:
                limit = PER_MODEL_CONCURRENCY.get(model, DEFAULT_MODEL_CONCURRENCY)
                self.semaphores[model] = threading.Semaphore(limit)
            return self.semaphores[model]

    def log(self, kind: str, record: dict[str, Any]) -> None:
        record = {
            "kind": kind,
            "ts": datetime.now(UTC).isoformat(timespec="seconds"),
            **record,
        }
        with self.log_lock:
            self.log_file.write(json.dumps(record, ensure_ascii=False) + "\n")
            self.log_file.flush()

    def call(
        self,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int = 1000,
        context: dict[str, Any] | None = None,
    ) -> CallResult:
        """One chat completion, with up to 4 attempts.

        ``context`` identifies the chain and role; it is included in the
        per-attempt log records so every HTTP request (including the failed
        ones, which may still have cost money) is traceable in calls.jsonl.

        Returns a dict with 'content' on success or 'error' after the last
        attempt fails. Empty responses and HTTP errors both count as
        failures and are retried with a growing pause; a 429's Retry-After
        header is honored when present.
        """
        context = context or {}
        body = json.dumps(
            {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
            }
        ).encode()

        last_error = None
        with self._semaphore_for(model):
            for attempt in range(1, 5):
                if ABORT.is_set():
                    return {"error": "aborted", "model_requested": model}
                attempt_log = {**context, "model_requested": model, "attempt": attempt}
                try:
                    request = urllib.request.Request(
                        f"{API}/chat/completions",
                        data=body,
                        method="POST",
                        headers={
                            "Authorization": f"Bearer {self.key}",
                            "Content-Type": "application/json",
                            "X-Title": "adapter-semantics-experiment",
                        },
                    )
                    started = time.time()
                    with urllib.request.urlopen(request, timeout=180) as r:
                        response = json.load(r)
                    attempt_log.update(
                        {
                            "model_served": response.get("model"),
                            "provider": response.get("provider"),
                            "usage": response.get("usage"),
                            "latency_s": round(time.time() - started, 2),
                        }
                    )
                    if not response.get("choices"):
                        raise ValueError(f"no choices: {json.dumps(response)[:300]}")
                    content = response["choices"][0]["message"]["content"]
                    finish = response["choices"][0].get("finish_reason")
                    attempt_log["finish_reason"] = finish
                    if not content or not content.strip():
                        raise ValueError("empty content")
                    attempt_log["ok"] = True
                    self.log("attempt", attempt_log)
                    if model.startswith("stealth/"):
                        ABORT.wait(3)  # courtesy pause on the free tier
                    return {
                        "content": content,
                        "finish_reason": finish,
                        "model_requested": model,
                        "model_served": response.get("model"),
                        "provider": response.get("provider"),
                        "usage": response.get("usage"),
                        "latency_s": attempt_log["latency_s"],
                        "attempt": attempt,
                    }
                except urllib.error.HTTPError as e:
                    last_error = e
                    attempt_log.update(
                        {"ok": False, "http_status": e.code, "error": str(e)}
                    )
                    self.log("attempt", attempt_log)
                    retry_after = e.headers.get("Retry-After")
                    if retry_after and retry_after.isdigit():
                        pause = int(retry_after)
                    else:
                        pause = 8 * attempt
                    ABORT.wait(pause)  # returns early if aborted
                except Exception as e:  # noqa: BLE001 — every failure retries
                    last_error = e
                    attempt_log.update({"ok": False, "error": str(e)})
                    self.log("attempt", attempt_log)
                    ABORT.wait(8 * attempt)
        return {"error": str(last_error), "model_requested": model}


def account_credits(key: str) -> float | None:
    """Remaining OpenRouter credit in dollars, or None if unreachable."""
    try:
        request = urllib.request.Request(
            f"{API}/credits", headers={"Authorization": f"Bearer {key}"}
        )
        with urllib.request.urlopen(request, timeout=20) as r:
            data = json.load(r)["data"]
        return round(data["total_credits"] - data["total_usage"], 4)
    except Exception:  # noqa: BLE001
        return None
