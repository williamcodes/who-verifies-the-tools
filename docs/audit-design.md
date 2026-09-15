# Audit-prompt demonstration: design note

Written 2026-08-27, before any run. Status: proposed design; no results yet.

## What this is

A demonstration for the conclusion section: an off-the-shelf coding agent (Codex),
given a frozen audit prompt (`PROMPT.md`), audits the source system's pre-fix tree
and we report what it found. It is not an evaluated method. One system, a prompt
written by the authors for that system, no generality claim.

## Target

`snapshot-66a6fa2/`: the source repository exported at commit `66a6fa2` with no
`.git` directory. Checked 2026-08-27: no repository history present; no
documentation in the snapshot describes the defects (the only "disclosure" match
is an unrelated UI roadmap item).

Ground truth at this commit:

- LIVE, scope (F1): `rag.py` no-hit branch says "FULL text" while
  `db_manager.py` caps each field scan at 1,000,000 characters.
- LIVE, completeness (F2): `date_range_search` output begins "Found 20
  document(s)" with no total; limit 20 at `rag.py:713`.
- NOT live, uncertainty (F3): shipped page-number estimates are labeled. The
  unlabeled form studied in the experiment never shipped. The agent can at most
  flag the estimation as a hazard.
- NOT live, provenance (F4): the `a50d9cd`-era identifier fix predates this
  commit. The overlapping document/scan ID namespaces still exist structurally;
  the agent can at most flag the hazard.

Therefore the strongest achievable true sentence is: "found both live defects,"
optionally "and flagged the estimate and identifier-namespace hazards." A
sentence claiming the prompt found four live defects would be false and must not
appear in the paper.

## Protocol

1. Prompt frozen in `PROMPT.md` before the first run.
2. One Codex run, read-only, launched by William, cwd = the snapshot directory.
   No git history, no network requirement, no production logs (the prompt's log
   step falls through to its code-only branch).
3. Raw output saved verbatim to `research/audit-demo/runs/` before any judgment.
4. Scoring: did the report identify the F1 formatter and its cap omission; did it
   identify the F2 formatter and its missing total; did it flag the F3 estimate
   or F4 namespace hazards; what else did it flag (report all of it, including
   noise).
5. Report the actual outcome. If the run misses, the miss is the result. A second
   run happens only with a written reason here, and both runs are then reported.

## Launch log

- 2026-08-27, attempts 1-3: CLI launch failures (prompt parsed as a flag; then
  leftover empty files blocking noclobber redirects). Codex never received the
  prompt; not runs.
- 2026-08-27, attempt 4: Codex started, and its first action was to grep its own
  persistent memory (`~/.codex/memories/MEMORY.md`), which contains notes on this
  paper and on the source system — including the F1 cap and its planned removal
  (memory line 2276). Killed before it produced a report. VOIDED for
  contamination; the demonstration requires an auditor without prior knowledge of
  the defects.
- Run 1 proper: relaunched with `--disable memories` so the agent cannot read its
  persistent memory. The paper must state the agent ran with memory disabled;
  any practitioner reusing the prompt on a system their agent has previously
  worked on faces the same contamination issue, which is worth a sentence.

## Run 1 score (2026-08-27, `runs/20260827-codex-run1-raw.md`)

- F1 (live): FOUND, exact. Finding 1 identifies the "FULL text" no-hit message,
  the 1,000,000-character cap, and the early return that skips the cap
  disclaimer — the same three source locations as our audit. It also adds that
  found-result counts undercount past the cap.
- F2 (live): FOUND, exact. Finding 3 identifies "Found 20 document(s)" with
  `limit=20` and no computed total, plus the retrospective-date wording issue.
- F3 hazard (labeled estimates): NOT flagged.
- F4 hazard (ID namespaces): NOT flagged.
- Additional findings: 6 (semantic_search 3-of-5, visual_search cap/empty
  semantics, keyword snippet substitution, read_page_scans silent filtering,
  get_document omitted fields, set_ui_language premature completion).
  All six VERIFIED against the snapshot source (2026-08-27):
  - semantic_search 3-of-5: rag.py:170 default `max_docs=3` slices a 5-result
    fetch from rag.py:650; no truncation notice.
  - visual_search: `limit=12` hardcoded at rag.py:869; ranked walk keeps top-12
    eligible with no similarity threshold (db_manager.py:660-695); formatter
    prints "Found N visually similar page scan(s)" with no cap note and "No
    visually similar scans found." for the empty branches.
  - keyword snippet: `_build_snippet` falls back to the field's first ~40 words
    when no span is located (db_manager.py fallback branches), and rag.py:267
    labels that text "Match context:".
  - read_page_scans: rag.py:784 filters invalid pages silently; error message
    only when every requested page is invalid (behavior verified; Codex's
    example output string not independently rendered).
  - get_document: `_format_document_detail` prints no summary or
    item_description field; "Full original transcript (N chars)" precedes an
    8,000-character display with an explicit truncation warning (Codex's
    characterization matches).
  - set_ui_language: rag.py:918 appends to `ui_commands` and returns
    "Interface language switched to ..." having only queued the command.

Honest summary sentence the result supports: given the frozen prompt, Codex
found both defects that were live at the pre-fix commit, missed the two
studied hazards that had already been fixed, and reported six further
discrepancies outside our catalogue, at least one of which is real.

## Claude Code run score (2026-08-28, `runs/20260828-claude-opus-run1-raw.md`)

Harness: Claude Code headless (`claude -p --model claude-opus-5`), same frozen
prompt, same snapshot. Caveats: user-level ~/.claude/CLAUDE.md (writing-style
instructions, no defect content) could not be disabled; the agent built a
fixture DB and executed the snapshot's tool code in <local-path>/audit (left no
source modification — checked: no .py newer than run start; only __pycache__
from imports, removed). Its quoted outputs are executed-harness outputs, not
constructed readings.

- F1 (live): FOUND, exact, deeper than Codex — adds that `transcript_chars`
  prints the full length beside "Searched the FULL text", corroborating the
  false claim, and chains it with the snippet fallback to reproduce the
  historical retraction incident.
- F2 (live): FOUND, exact — including that the SQL has no LIMIT, so the code
  holds all matching rows and discards the true total, and the
  date-ascending selection bias.
- F3 hazard: correctly reported CLEAR (found-branch labels estimates).
- F4 hazard: not flagged as doc/scan substitution; adjacent finding on
  `get_document_by_item` asserting nonexistent items were "not transcribed".
- 13 findings total. Overlapping Codex run 1 (already verified by us):
  semantic 3-of-5, snippet fallback, read_page_scans silent filtering,
  set_ui_language, visual_search caps. New beyond Codex (verified by the
  run's own executed harness, NOT yet independently verified by us):
  synthesizer 4,000-char cut strips guard-rail warnings; transcript_quality
  is a 500-char-prefix rating presented as whole-document; "English
  translation" covers only the first 8,000 source chars; "Transcript
  excerpt" may be an LLM summary; persons/places labeled catalog metadata in
  one formatter, bare in three.

2026-08-29: the assembly audit noted that Codex's unique get_document
omitted-fields finding had no adversarial-review artifact (it had only my
direct source verification). A dedicated xhigh validator was run:
CONFIRMED (`validation/results/F14-getdoc.md`), including the
contradictory "Full original transcript" label. All twelve distinct
additional discrepancies now carry adversarial model review.

Both harnesses, same frozen prompt, found both live defects independently.
The paper may now say "coding harnesses (Codex and Claude Code)" in the
plural for the rediscovery demo. Per-finding citation of the Claude-only
findings requires our own verification first.

## Paper placement

- Conclusion: the result in one or two sentences, plus the prompt (or an
  appendix box), with the authorship disclosure.
- Section 6 limitation: demonstrated once, on one system, by the system's
  authors, with a prompt written knowing the defects.
- Abstract: at most one clause, only after the run, describing what actually
  happened.

## Ledger

Tracked as C07, status `untested` until the run artifact is saved.
