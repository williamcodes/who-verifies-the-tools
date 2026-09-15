# Verification report

This report records the preservation checks for the public repository.

Verified on 2026-09-15 against source workspace commit `00c879016ac125100dab96c76cf701e8ed972a0c`.
The original workspace and the external archive source were not edited. No live
model requests or database reconstruction ran during the refactor.

## Clean-checkout result

The original suite passed all 26 tests before edits. The public suite contains
95 tests, including those 26 original test bodies. All 95 pass in an isolated checkout
on Python 3.12.8 and 3.14.6 with site packages disabled. The test environment has no
archive checkout, ignored snapshot, `.env` file, or API credentials. Network access
is blocked in the verification process. Child CLI checks only import modules,
display help, or perform offline replay.

Both checks left every exported file byte-identical to its pre-test state. [GitHub
Actions](https://github.com/williamcodes/who-verifies-the-tools/actions/workflows/tests.yml)
runs the same command on each push and pull request.

```bash
python3 -S -B -m experiment verify
```

The tests cover all four builders, formatter disclosures, altered inputs and hashes,
prompt preservation, failed grades, denominators, holdout selection, bootstrap
outputs, retries and aborts, both harness orchestration paths, checkpoints, resume
rejections, source/migration guards, and human-grading records.

## Byte preservation

All three original `cases/` files are preserved exactly:

| File | SHA-256 |
|---|---|
| `checker_report.json` | `dc2d3b9e9c02a6f15c5eaf38822e27c7ab311313c46ede05a7a7c2b1cf1fe751` |
| `manifest.json` | `e340c2e3d9a991cad12300d29ff990591110b1740fae92a33c28fef208c64c9b` |
| `preview.md` | `41d1a73be20cc4fa0dabc871503656059ec55bd6b3fabd0a0ab923bc31acf870` |

All 80 embedded rendering hashes match. Both historical formatters reproduce all
40 F1/F2 A/B renderings. F3/F4 transforms reproduce all 20 A renderings from B.
The checker regenerates the original report: 40/40 A texts flagged, 0/40 B texts
flagged. Tests also verify that the vendored source functions and field-label
constant are verbatim copies of the pinned archive source.

The prompt fingerprint is `bb93d9d2c190e826bbe083799716f154edd5bc1c34d36c2ffea6eda1ef050ce5`. Tests compare it and each original
system/user template with the pre-refactor baseline.

## Original-versus-refactored outputs

Before changing the exported builder, the original builder ran against synthetic
SQLite rows and scripted tool results with a fixed UTC clock. Its complete manifest
and preview outputs were saved under [tests/fixtures/builder/](../tests/fixtures/builder/).
The refactored builder generates the same bytes for all four case families.
Unverified-provenance output is also compared against original output hashes.
Invalid counts, duplicate IDs, identical A/B texts, shifted evidence, short pages,
changed totals, and incorrect scan collisions are covered by rejection tests.

The fixture data exercises original selection rules; it is not historical archive
data. [provenance.json](../experiment/provenance.json) records the source
commit, original code hashes, fixture hash, and expected output hashes.

The original analyzer was also run in scratch space on the full and fixed-answer
runs. Its reports matched the recorded reports. The refactored analyzer reproduces
both reports and the full run's human sample byte-for-byte. The human-grading summary
is reproduced field-for-field except its generation timestamp: 40 graded, 36 in
scope, 35 agreements, one disagreement.

## Limits preserved with the evidence

- The archived preview contains ten F2 questions from before the final wording.
  Its differences from a current preview are tested explicitly. Offline replay
  copies the historical preview unchanged; the manifest contains the final questions.
- F3/F4 B renderings are frozen evidence because their complete database inputs were
  not saved. Replay verifies their hashes and reconstructs A; it does not rebuild B
  from a database.
- The database builder stamps the current time, while the final manifest contains a
  later provenance annotation. Controlled differential tests prove equivalence under
  identical inputs and time. They do not prove a fresh historical database rebuild.
- Disclosure checks establish the presence of known wording, not the truth of the
  underlying claim. Fixed-answer causal comparisons and whole-answer operational
  comparisons retain their original distinction.
- Historical raw API call logs are excluded, so request-level retries, provider
  responses, and the paper's total spend cannot be fully audited from this export.

## Source and layout

Condition A uses the defective F1/F2 formatters from archive commit
`66a6fa2bb3f66a2c1edced16b805fd749340ba6c`. Condition B uses five formatter and helper
functions plus `_FTS_FIELD_LABELS` from
`8364f2281ab31c9f13a0486a0395221da80fab53`. Tests compare their verbatim source hashes.
The historical database entrypoint loads the external archive application; offline
verification imports only the extracted standard-library code.

Code lives in `experiment/`, recorded evidence in `data/`, and paper and protocol
files in `docs/`. The directory move changes imports and default artifact paths.
All retained data files, all eight paper sections, experimental protocols, prompts,
and the original regression expectations retain their pre-move bytes.

The public tree excludes literature reading notes and PDFs, the podcast transcript,
claim ledger, predictions, inherited-evidence narrative, conference submission
material, issue and pull-request drafts, six smoke-run directories, and earlier
export inventories and cleanup reports. Pilot runs remain because they document
changes to the grading instrument and the paper's calibration claims. Final runs,
human grades, and audit findings remain because they support reported results.

Machine-specific paths in the initial export's audit reports and database-location
fields were redacted. Historical source paths quoted inside evidence still identify
the audited checkout, rather than this repository's current layout.
