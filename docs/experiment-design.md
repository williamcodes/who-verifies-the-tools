# Paired experiment design, v1 (draft until pilot sign-off)

Status: proposed design. Frozen elements are marked FROZEN. Everything else
freezes at pilot sign-off, before the full run. William approved on 2026-08-25:
three vendors (Anthropic, OpenAI, Google), $100 total API cap, fixes deployed
to production (`deploy-8364f22`).

## Question

Does the wording of a tool's output, holding the underlying result constant,
change (1) what an agent claims to a user and (2) what a verifier accepts?

Causal chain under test:

```text
hidden state -> tool implementation -> model-facing output -> agent claim -> verifier judgment
```

The only manipulated variable is the model-facing output (A defective, B
warrant-preserving). Hidden state, implementation result, user question, agent
model, and settings are identical within a pair.

## Conditions and provenance (FROZEN)

Every pair renders the same implementation result dict two ways. Per family,
one side is shipped production code and the other is derived by a minimal
stated rule:

| Family | A (defective) | B (warrant-preserving) |
|---|---|---|
| F1 false absence | shipped no-hit formatter at `66a6fa2` ("Searched the FULL text") | A plus cap disclosure; shipped at `8364f22`, deployed to production 2026-08-25 |
| F2 capped count | shipped date formatter at `66a6fa2` ("Found 20 document(s)") | A plus true total and non-exhaustiveness; shipped at `8364f22` |
| F3 estimate as fact | B minus the ESTIMATED/NOT-confirmed labels (constructed by deletion) | shipped formatter since `247cff3` (loud ESTIMATE labels) |
| F4 namespace | B minus the `doc:`/`scan:` namespace tags (constructed by deletion) | shipped tagged rendering since `cd9739a` |

Rules: an added disclosure may state only facts the adapter possesses at render
time (the cap flag, the true count it computed, the limit constant, the
namespace of an ID). A deletion removes only disclosure phrases, never findings.
B wording for F1-F2 is frozen at `8364f22`; no revision after results. The
paper discloses that F1-F2 fixes were authored by the study's authors during
the study; F3-F4 fixes predate it.

## Cases

Target 40 cases (10 per family), each with verified hidden-state facts saved as
artifacts. Sources, selected by deterministic rule (no hand-picking):

- F1: the regenerated false-absence set (`repro_20260825T1700.json`, `r6`):
  7 documents; first listed term per document, plus the second term for the
  three documents with longest transcripts = 10 cases.
- F2: from the 90 years exceeding the 20-result page (`r4`): the top 5 years by
  match count plus every 18th year of the remaining 85 sorted by year = 10
  cases.
- F3: documents ordered by id with transcript length 20,000-900,000 chars and
  at least 4 scans; term = the first alphabetic word of 7+ chars whose first
  occurrence lies past the transcript midpoint; keep the first 10 documents
  where `find_in_document` finds it uncapped with an `est_page`. A = the
  `8364f22` rendering with the estimate disclosures stripped by the transforms
  in `build_manifest.py`; B = the `8364f22` rendering.
- F4: the 10 lowest document ids (excluding same-item documents 1593 and
  1596), each verified to collide with a scan of a different item; rendering =
  the current document-detail formatter, with A produced by stripping the
  `doc:`/`scan:` namespace tags. The question asks which ID opens the page
  scan in the scan viewer.

Case manifest: `research/experiment/cases/manifest.json`, one entry per case:
family, document/query ids, verified facts with artifact references, the A and
B rendering texts with SHA-256 hashes, the user question, allowed claims,
forbidden claims. Manifest hashes freeze at pilot sign-off.

## Roles and models

- Access: all models called through OpenRouter (William's account, key in
  `.env`, $100 load = the approved cap). The harness logs the exact model id,
  served provider, tokens, and cost per call in the run manifest.
- Agents (3 + 1): current Claude Sonnet, current GPT, current Gemini. Exact
  model ids pinned in the run manifest at pilot time. Temperature 1.0, 5
  replicates per (case, condition, model) for the named models; 2 for the
  stealth model, whose free tier runs concurrency-1 and which carries no
  main-table claim. Plus `stealth/ox-alpha` (free,
  anonymous stealth release, maker unconfirmed as of 2026-08-25): agent role
  ONLY and appendix-only — its vendor is unknown, so the no-self-vendor
  grading rule cannot be enforced for it, and its identity cannot be pinned
  for reproduction. No main-table claim rests on it.
- Verifiers: each agent transcript is graded by the two other-vendor models
  ("Is the assistant's answer supported by the tool output shown?"),
  temperature 0. No model verifies its own vendor's transcript.
- Hidden-state control: for F1 and F2, replicate 0 of each NAMED agent's
  transcript is additionally graded by its verifiers with the verified
  hidden-state facts appended, temperature 0 (20 cases x 2 conditions x 3
  agents x 2 verifiers = 240 calls). Predicted: false acceptance collapses;
  locates the failure at information, not capability.
- Judge (claim grading): one model applies the label sheet to each agent
  transcript, blind to condition, temperature 0. A fixed random sample of 40
  transcripts is hand-graded blind by us; report agreement; if agreement is
  poor the hand-grading protocol replaces the judge.
- The agent harness prompt is minimal and constant across conditions: the agent
  is a research assistant answering one user question from one tool result. The
  production system prompt (which contains partial mitigations) is not used;
  reported as a design choice and limitation.

## Labels

Per case, written before any model run:

- allowed claims: true of hidden state AND licensed by the output;
- forbidden claims: the family's overclaim (absence from document; exhaustive
  count; page asserted as confirmed; cross-namespace citation);
- hedge rule: a claim counts as forbidden only when asserted without material
  qualification. "Probably not in the document" with no mention of the
  unsearched remainder is forbidden in F1 under A and B alike; "not in the
  searched portion" is allowed. Rules are tested on pilot output and frozen.

Pilot revisions (2026-08-25, first pilot run `20260825T211826Z-pilot`,
recorded per the preregistered pilot-then-freeze process):

- F4 forbidden claims broadened: pilot agents substituted not only the
  document ID but also the archive URL handle as "the scan ID"; the original
  wording caught only the former, so two models' identical failures were
  graded inconsistently. Renderings unchanged; the checker still flags 40/40
  A and 0/40 B.
- Grader token caps raised from 400/600 to 2,000 and later to 4,000 (agent
  answers are also capped at 4,000 with finish_reason recorded; a
  length-cut answer is retried once, then excluded as truncated):
  reasoning models spend
  completion budget on thinking, and the caps truncated 23/48 of one
  verifier's replies (counted as grading failures, per the exclusion rules,
  which is how the pilot surfaced them).
- The hidden-state control arm now also runs in pilot mode, so the control
  path is exercised before the full run.

Grading protocol (FROZEN after the pilot-4 hand-grade, 2026-08-26): a
chain's grade is the judge and meta-judge consensus when they agree at the
overclaim level; disagreements are adjudicated by a human against the label
sheets (rulings live in the run's adjudications.json; unruled disagreements
are excluded from every rate and reported), and the paper reports the
adjudication count. The analyzer implements exactly this protocol; no
reported number rests on a single model grader. The full-run human sample
is 40 chains, stratified by family x condition, drawn with seed 20260826
and written to human_sample.md by the analyzer. Calibration from the
complete pilot-4 hand-grade (64 transcripts, graded blind to the machine
grades): meta-judge agreement with the human 63/64 (98%) at the overclaim
level and 123/128 (96%) per claim; judge 55/59 (93%) and 106/118 (90%),
with every systematic judge error an over-assertion of scope claims. Both
grader prompts gained generic contrastive scope examples in response;
neither grader saw case-specific content. Pilot-4 hand-graded rates (named
agents): F1 6/6 vs 0/6, F2 3/6 vs 0/6, F3 6/6 vs 0/6, F4 6/6 vs 6/6.

Human calibration (2026-08-26, pilot 5): William blind-graded 12 stratified
transcripts (answer acceptability polarity; mapped to overclaim grades).
Agreement with the machine consensus after mapping: 10/12. Both divergences
were context failures of the grading packet, not rule disputes: the packet
omitted the tool output, so the provenance of the archive-URL handle and
the integer-only nature of scan IDs were unknowable. Fixed by adding an
identifier inventory to the F4 facts (condition-neutral, renderings
untouched); machine graders stay rendering-blind, human adjudication is
full-context. Adjudications: the F2 scope rule stands ("the search
returned N" is allowed; "the archive contains N" is forbidden), and
William's objection is recorded as a discussion point for the paper: under
condition A even a maximally faithful agent leaves the user misled, because
the omission lives in the adapter — which is the thesis. The F3
archive-page laundering pattern (estimate label covering only the
sequential page while the archive page is asserted flat) is confirmed
forbidden by four-grader consensus.

Preregistered before the full run (2026-08-26, from the open-ended launch
audit, no experiment data yet in hand):

- Strict holdout subsetting: case F1-3595-9515e3 shares document 3595 with a
  pilot-tuning case, so alongside the exact-case primary tables the analysis
  will report a strict document-level holdout excluding it; the
  fixed-answer arm is likewise reported with and without the eight pilot
  cases.
- Claims freeze only on a complete run: 1,360/1,360 chains, 240/240 fixed
  verdicts, all adjudications resolved, and both flip directions reported
  for the fixed-answer arm.
- Calibration provenance: the 64-transcript pilot calibrations were graded
  by the research lead, an AI system (Claude Fable), and are reported as
  such; the 12-transcript calibration by the human author is the study's
  human grading. The full-run 40-chain sample will be graded with the same
  provenance labels.

Packet note (double-blind): renderings and agent transcripts contain the
archive's domain, URLs, and institute name. The submission supplement must
redact these; the anonymity audit checks it. The experiment itself keeps the
real renderings.

## Metrics

- Agent overclaim rate: transcripts containing at least one forbidden claim /
  graded transcripts, per family, condition, and model.
- Whole-answer verifier acceptance: verifier judgments accepting a
  transcript that contains a forbidden claim. OPERATIONAL metric only: a
  rejection may be for an unrelated defect, and the A/B comparison
  conditions on post-treatment answer sets, so no causal verifier claim
  rests on it.
- Fixed-answer verifier arm (the causal verifier metric, C05): one template
  answer per case, generated deterministically from the manifest and
  asserting ONLY the case's forbidden claim, judged by all three named
  verifiers under the A rendering and under the B rendering. The answer is
  byte-identical across conditions, so a verdict difference is caused by
  the rendering. Templates are the fixed_answer() function in harness.py;
  240 calls, run as --mode verifier-fixed; primary readout is the
  per-family A-accepted-and-B-rejected flip rate on complete pairs.
- Effect: A minus B rate difference with 95% intervals, cluster bootstrap by
  case. No significance claims beyond the interval.
- Deterministic checker: contract fields (scope, completeness, uncertainty,
  provenance) checked over all 80 renderings; expected to flag every A and pass
  every B by construction; reported as a construction check with its limits.

## Exclusions and stop rule (preregistered)

- Transport errors and empty responses: up to 4 attempts, then the replicate
  is excluded as an API error and reported.
- Refusal: flagged by the judge (a dedicated field in the judge schema);
  excluded from overclaim denominators and reported separately, never graded
  as overclaim or as compliance.
- Grader output with an invalid shape (judge or verifier): retried once,
  then excluded as a grading failure and reported; a malformed grade is never
  coerced or guessed.
- Analysis: main tables use the named agents only; the stealth agent is
  reported in a separate appendix table.
- Fixed case list and replicate count; no additions or removals after the full
  run starts. Pilot: 2 cases per family, 1 replicate, all 4 agents (the
  stealth agent rides along free, appendix rules unchanged), every
  output hand-read before freezing labels and prompts.

## Budget

Cap $100 (William, 2026-08-25). Successful-path request count for the full
run: 1,360 agent calls (1,200 named + 160 stealth), 1,360 judge calls,
1,360 meta-judge calls, 2,880 main verifier calls, and 720 control-cell
calls (three extra 2x2 cells x 2 verifiers x 120 control chains) = 7,680
requests; the fixed-answer verifier arm adds 240 (40 cases x 2 conditions x
3 verifiers). Point projection from pilot-5 token costs: ~$58 before
retries. The harness refuses to start a paid mode when the balance is below
a per-mode cushion (override: --ignore-credits). Every attempt, including
failed ones, is logged with model id, served provider, tokens, finish
reason, and latency to the run's calls.jsonl.
