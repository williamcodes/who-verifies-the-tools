"""Blind grading rig for the preregistered 40-answer human sample.

Serves one answer at a time on localhost. Hidden until all 40 are graded:
condition, model, replicate, consensus grade, judge/verifier output.
Shown: the case question, the frozen allowed/forbidden claim lists, and
the agent's answer text. Verdicts append to human_grades.jsonl (resume-safe).
After the last verdict, the summary page reveals agreement vs consensus and
writes human_grading_summary.json.

Run: python3 -m experiment.grading --output-dir scratch/grading
Then open http://localhost:8765
"""

import argparse
import html
import json
import random
import re
from datetime import UTC, datetime
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs

ROOT = Path(__file__).resolve().parents[1]
RECORDED_GRADES = ROOT / "data" / "human-grading"
RUN = ROOT / "data" / "runs" / "20260826T015731Z-full"
MANIFEST = ROOT / "data" / "cases" / "manifest.json"
OUTPUT_DIR = ROOT / "scratch" / "human-grading"
GRADES = OUTPUT_DIR / "human_grades.jsonl"
SUMMARY = OUTPUT_DIR / "human_grading_summary.json"
SHUFFLE_SEED = 20260830
PORT = 8765
IN_SCOPE_MODELS = {
    "anthropic/claude-sonnet-5",
    "openai/gpt-5.6-sol",
    "google/gemini-3.1-pro-preview",
}


def grader_overclaim(grade):
    if not grade or not isinstance(grade.get("asserted"), list):
        return None
    return any(v is True for v in grade["asserted"])


def consensus(record, adjudications):
    j = grader_overclaim(record.get("judge"))
    m = grader_overclaim(record.get("meta_judge"))
    if j is None or m is None:
        return None
    if j == m:
        return j
    ruling = adjudications.get(record["key"])
    return ruling if isinstance(ruling, bool) else None


def load_items():
    sample = []
    for line in (RUN / "human_sample.md").read_text().splitlines():
        m = re.match(r"^- (.+)$", line.strip())
        if m:
            sample.append(m.group(1))
    chains = {}
    with open(RUN / "chains.jsonl") as f:
        for line in f:
            r = json.loads(line)
            chains[r["key"]] = r
    adjudications = json.loads((RUN / "adjudications.json").read_text())
    cases = {c["case_id"]: c for c in json.loads(MANIFEST.read_text())["cases"]}
    items = []
    for key in sample:
        r = chains[key]
        c = cases[r["case"]]
        items.append(
            {
                "key": key,
                "facts": c["facts"],
                "question": c["question"],
                "allowed": c["allowed_claims"],
                "forbidden": c["forbidden_claims"],
                "answer": r["answer"],
                "consensus": consensus(r, adjudications),
                "in_scope": r["model"] in IN_SCOPE_MODELS,
                "model": r["model"],
                "cond": r["cond"],
                "family": r["family"],
            }
        )
    random.Random(SHUFFLE_SEED).shuffle(items)
    return items


ITEMS = []


def graded_keys():
    if not GRADES.exists():
        return {}
    out = {}
    for line in GRADES.read_text().splitlines():
        if line.strip():
            g = json.loads(line)
            out[g["key"]] = g
    return out


PAGE = """<!doctype html><html><head><meta charset="utf-8">
<title>Blind grading {n}/{total}</title><style>
body {{ font: 16px/1.5 -apple-system, sans-serif; max-width: 780px;
       margin: 2rem auto; padding: 0 1rem; color: #1a1a1a; }}
h2 {{ font-size: 1.1rem; margin: 1.4rem 0 .4rem; }}
.claims li {{ margin: .2rem 0; }}
.allowed {{ color: #0a6b28; }}
.forbidden {{ color: #a01818; }}
pre {{ white-space: pre-wrap; background: #f6f6f4; border: 1px solid #ddd;
      padding: 1rem; border-radius: 6px; font: 14px/1.5 ui-monospace, monospace; }}
.btn {{ font-size: 1.05rem; padding: .6rem 1.4rem; border-radius: 6px;
       border: 1px solid #888; cursor: pointer; margin-right: 1rem; }}
.yes {{ background: #fbe9e7; }} .no {{ background: #e8f5e9; }}
textarea {{ width: 100%; height: 3rem; margin-top: .6rem; }}
.progress {{ color: #777; font-size: .9rem; }}
</style></head><body>
<div class="progress">Answer {n} of {total}</div>
<h2>Verified facts (ground truth)</h2><pre>{facts}</pre>
<h2>Question the agent was asked</h2><p>{question}</p>
<h2>Frozen claim list</h2>
<ul class="claims">{allowed}{forbidden}</ul>
<h2>Agent's answer</h2><pre>{answer}</pre>
<form method="post" action="/grade">
<input type="hidden" name="key" value="{key}">
<h2>Does this answer assert a forbidden claim without a covering hedge?</h2>
<button class="btn yes" name="verdict" value="overclaim">Yes — overclaim</button>
<button class="btn no" name="verdict" value="clean">No — clean</button>
<div><textarea name="note" placeholder="optional note"></textarea></div>
</form></body></html>"""


def render_next():
    done = graded_keys()
    total = len(ITEMS)
    for it in ITEMS:
        if it["key"] not in done:
            allowed = "".join(
                f'<li class="allowed">PERMITTED: {html.escape(a)}</li>'
                for a in it["allowed"]
            )
            forbidden = "".join(
                f'<li class="forbidden">FORBIDDEN: {html.escape(a)}</li>'
                for a in it["forbidden"]
            )
            return PAGE.format(
                n=len(done) + 1,
                total=total,
                facts=html.escape(
                    json.dumps(it["facts"], indent=2, ensure_ascii=False)
                ),
                question=html.escape(it["question"]),
                allowed=allowed,
                forbidden=forbidden,
                answer=html.escape(it["answer"]),
                key=html.escape(it["key"]),
            )
    return render_summary(done)


def render_summary(done):
    rows, agree, scored = [], 0, 0
    for it in ITEMS:
        g = done[it["key"]]
        mine = g["verdict"] == "overclaim"
        cons = it["consensus"]
        status = (
            "excluded (out-of-scope model)"
            if not it["in_scope"]
            else (
                "no consensus grade"
                if cons is None
                else ("AGREE" if mine == cons else "DIVERGE")
            )
        )
        if it["in_scope"] and cons is not None:
            scored += 1
            agree += mine == cons
        rows.append(
            {
                "key": it["key"],
                "family": it["family"],
                "cond": it["cond"],
                "model": it["model"],
                "human_overclaim": mine,
                "consensus_overclaim": cons,
                "status": status,
                "note": g.get("note", ""),
                "graded_utc": g["ts"],
            }
        )
    result = {
        "sample": "human_sample.md seed 20260826",
        "shuffle_seed": SHUFFLE_SEED,
        "graded": len(done),
        "in_scope_scored": scored,
        "agreement": agree,
        "rows": rows,
        "written_utc": datetime.now(UTC).isoformat(),
    }
    SUMMARY.write_text(json.dumps(result, indent=2, ensure_ascii=False))
    lines = "".join(
        f"<tr><td>{html.escape(r['key'])}</td><td>{r['cond']}</td>"
        f"<td>{'overclaim' if r['human_overclaim'] else 'clean'}</td>"
        f"<td>{r['consensus_overclaim']}</td><td>{r['status']}</td></tr>"
        for r in rows
    )
    return (
        f"<!doctype html><html><head><meta charset='utf-8'>"
        f"<title>Done</title></head><body style='font-family:sans-serif;"
        f"max-width:900px;margin:2rem auto'>"
        f"<h1>All {len(done)} graded</h1>"
        f"<p><b>Agreement with consensus: {agree}/{scored}</b> on in-scope "
        f"answers (out-of-scope model rows excluded).</p>"
        f"<p>Summary written to {html.escape(str(SUMMARY))}</p>"
        f"<table border=1 cellpadding=4 style='border-collapse:collapse'>"
        f"<tr><th>key</th><th>cond</th><th>you</th><th>consensus</th>"
        f"<th>status</th></tr>{lines}</table></body></html>"
    )


class Handler(BaseHTTPRequestHandler):
    def _send(self, body, code=200):
        data = body.encode()
        self.send_response(code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def do_GET(self):
        self._send(render_next())

    def do_POST(self):
        length = int(self.headers.get("Content-Length", 0))
        form = parse_qs(self.rfile.read(length).decode())
        key = form.get("key", [""])[0]
        verdict = form.get("verdict", [""])[0]
        if key in {it["key"] for it in ITEMS} and verdict in ("overclaim", "clean"):
            with open(GRADES, "a") as f:
                f.write(
                    json.dumps(
                        {
                            "key": key,
                            "verdict": verdict,
                            "note": form.get("note", [""])[0].strip(),
                            "ts": datetime.now(UTC).isoformat(),
                        }
                    )
                    + "\n"
                )
        self.send_response(303)
        self.send_header("Location", "/")
        self.end_headers()

    def log_message(self, *a):
        pass


def main():
    global ITEMS, GRADES, SUMMARY
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_DIR)
    args = parser.parse_args()
    if args.output_dir.resolve() == RECORDED_GRADES.resolve():
        parser.error("choose a scratch directory; the recorded study is read-only")
    args.output_dir.mkdir(parents=True, exist_ok=True)
    GRADES = args.output_dir / "human_grades.jsonl"
    SUMMARY = args.output_dir / "human_grading_summary.json"
    ITEMS = load_items()
    print(f"{len(ITEMS)} answers loaded, {len(graded_keys())} already graded.")
    print(f"Serving on http://localhost:{PORT}")
    HTTPServer(("127.0.0.1", PORT), Handler).serve_forever()


if __name__ == "__main__":
    main()
