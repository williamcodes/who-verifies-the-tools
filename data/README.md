# Recorded evidence

These files record the submitted study. Dates, model names, upstream status, and
observations describe the historical runs.

| Evidence | Purpose |
|---|---|
| [Cases](cases/manifest.json) | Forty paired cases, facts, allowed and forbidden claims, and 80 rendering hashes. |
| [Full experiment](runs/20260826T015731Z-full/analysis.md) | Agent rates, bootstrap intervals, controls, and exclusions. |
| [Fixed-answer experiment](runs/20260826T015541Z-verifier-fixed/analysis.md) | Verifier judgments with the answer held fixed. |
| [Named-model grading statistics](runs/20260826T015731Z-full/named_grading_stats.json) | The paper's 1,147/1,199 grader agreement denominator. |
| [Human grades](human-grading/human_grades.jsonl) and [summary](human-grading/human_grading_summary.json) | Forty answers sampled, 36 in scope, 35 agreements, one disagreement. |
| [Source aggregates](reproductions/) | Recorded database facts used in case construction. |
| [Archive Codex audit](audits/archive-codex.md) and [Claude audit](audits/archive-claude.md) | Independent source audits. |
| [Validation prompts](audits/validation/prompts/) and [results](audits/validation/results/) | Adversarial reviews of the reported findings. |
| [OpenClaw](audits/openclaw.md) and [Hermes](audits/hermes.md) | Audits of two additional systems. |

## Why retain runs and grades?

`chains.jsonl` contains the observations underlying the analyses. Settings, summaries,
transcripts, hand grades, and adjudications let reviewers inspect how those
observations became reported results. Pilot runs document instrument tuning and
calibration; they should not be pooled with final results. Smoke runs are omitted.
Raw API call logs are also omitted, so request-level retries, provider responses,
and total spend cannot be fully reconstructed from this repository.

The [experiment design](../docs/experiment-design.md) records the grading rules and
exclusions. The [audit design](../docs/audit-design.md) includes the authors'
prior-knowledge disclosure; the [audit prompt](../docs/audit-prompt.md) is the frozen
research instrument. Model names in these records identify experimental tools.

## Preservation limits

The archived [preview](cases/preview.md) has ten older F2 questions. The manifest
contains the final questions; both files are preserved unchanged. F3/F4 B renderings
are frozen because their complete database inputs were not saved.

The full audited application snapshot is not distributed. Source paths and line
numbers inside audit reports identify historical code; they do not imply that the
corresponding source or scratch reproductions are included here.

See [verification](../docs/verification.md) for the original hashes and output
comparisons, and [reproduction commands](../docs/reproducing.md) to run the checks.
