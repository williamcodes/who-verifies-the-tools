You are an independent adversarial reviewer. Another model audited this codebase and reported the finding below. Your job is to VALIDATE or REFUTE it. Do not trust any quoted output or line number; re-derive everything from the source code in your working directory, and where the claim rests on runtime behavior, write and run a minimal reproduction (you may create scratch files and a fixture database; the directory is disposable). If line numbers are wrong but the substance holds, say so.

End your report with exactly one line:
VERDICT: CONFIRMED | REFUTED | PARTIAL — <one sentence>

The finding under review:

## Full-document retrieval omits searchable fields it has already loaded

7. Full-document retrieval omits searchable fields that it has already loaded

Formatter: `rag.py:453`

Both `get_document` and `get_document_by_item` use this formatter. The database result contains `summary`, `item_description`, `languages`, `item_id`, `source`, and other document columns (`db_manager.py:1469`). The formatter prints selected metadata and the two transcripts, but never prints those fields.

This matters because keyword search explicitly indexes summaries and item descriptions or photo captions. An agent following a keyword hit into `get_document` can see neither of those matching sources and may conclude that the reported match is unexplained or that the metadata is unavailable.

The label:

> Full original transcript (N chars):

also precedes only the first 8,000 characters. The formatter immediately provides an explicit truncation warning when needed, so this wording is contradictory but less likely to cause an unsupported absence claim.

