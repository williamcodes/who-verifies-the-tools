Confirmed. The cited line numbers also match this checkout.

- Both public tools pass enriched database rows to the same formatter: rag.py:720 (`rag.py:720`) and rag.py:731 (`rag.py:731`).
- Both database queries return `summary`, `item_description`, `languages`, and all document columns through `d.*`, including `item_id` and `source`: db_manager.py:1469 (`db_manager.py:1469`) and db_manager.py:1498 (`db_manager.py:1498`).
- The formatter prints selected metadata and transcripts but never reads those fields: rag.py:453 (`rag.py:453`).
- The FTS index includes summaries and item descriptions plus scan captions: db_manager.py:176 (`db_manager.py:176`).

A fixture database confirmed that both getters loaded all five disputed values, while the actual `get_document` and `get_document_by_item` tool outputs omitted every marker. Summary-only and item-description-only searches still matched and produced correctly attributed snippets.

The impact is slightly mitigated because keyword results themselves report the matching field and a context snippet at rag.py:250 (`rag.py:250`). Also, scan captions are fetched separately for search snippets and are not among the fields loaded by the full-document getters. Neither point changes the formatter defect.

The reproduction also confirmed that an 8,050-character transcript is labeled `Full original transcript (8050 chars)` while only 8,000 characters follow. The warning correctly reports the remaining 50 characters. The contradictory label therefore exists as reported. Relevant search tests passed, 36 in total.

VERDICT: CONFIRMED — Both full-document tools omit loaded searchable metadata, and the formatter labels a truncated transcript excerpt as full.
