I found eight model-facing output problems across the eleven tools. No production logs, traces, or database were present, so I used the formatter tests and representative formatter calls derived from the implementation.

## Findings

1. `find_in_document` can claim it searched full text after searching only the first 1,000,000 characters

Formatter: `rag.py:359`

Representative output:

> No occurrence of "needle" in document [doc:9]. Searched the FULL text: original transcript (1500000 chars), English translation, title, summary, persons/places metadata, and photo captions. [...] You may tell the user the term does not appear in the document's TRANSCRIPT.

The database truncates every searchable field to `_SNIPPET_SCAN_CAP`, currently 1,000,000 characters, before matching (`db_manager.py:1163`). It sets `scan_capped=True`, but the formatter returns from the absence branch before printing the cap warning at `rag.py:391`.

An agent would conclude that all 1,500,000 transcript characters and all other fields were searched, and that transcript absence was established. Occurrences after character 1,000,000 in any field remain unsearched.

The same cap also makes this found-result header potentially undercount:

> Found 1 occurrence(s) of "needle" in document [doc:9]

`total_matches` counts occurrences only in the scanned prefixes (`db_manager.py:1171`). The later cap note discloses partial searching, but the header still presents the count as the document-wide total.

2. `semantic_search` silently discards two of the five results it retrieves

Formatter: `rag.py:170`

The tool requests five results at `rag.py:650`. The formatter then iterates over `documents[:max_docs]`, where `max_docs` defaults to three.

Representative output from five inputs lists only:

> Document [doc:1]: Doc 1 (similarity: 0.99)  
> Document [doc:2]: Doc 2 (similarity: 0.98)  
> Document [doc:3]: Doc 3 (similarity: 0.97)

It contains no header or truncation notice. The underlying search calculates cosine similarity against the complete document-embedding matrix, then selects the top five (`db_manager.py:524`, `db_manager.py:536`).

An agent would not know that two higher-ranked results available to the tool were withheld. It may treat the three displayed documents as the complete result set.

3. `date_range_search` presents a capped page as an exact result count

Formatter: `rag.py:402`

At the cap, the output says:

> Found 20 document(s) from 1940-1940:

The tool always passes `limit=20` (`rag.py:713`). The database stops once it has accumulated 20 qualifying records and never computes the total (`db_manager.py:1439`, `db_manager.py:1451`).

The search also does not establish that documents were produced in the range. It accepts a document when one semicolon-separated `document_date` segment begins with a four-digit year inside the range (`db_manager.py:1443`). The tool description warns about retrospective dates, but the formatted phrase “documents from” does not preserve that qualification.

An agent could report that exactly 20 documents exist or that they were created in 1940. The code licenses neither conclusion.

4. `visual_search` hides its cap and mischaracterizes empty results

Formatter: `rag.py:430`

At the fixed tool limit, it says:

> Found 12 visually similar page scan(s):

The tool always requests at most twelve (`rag.py:869`). The search scores the embedding matrix, filters to scans joined to a document and any requested content classifications, and stops after twelve eligible scans (`db_manager.py:667`, `db_manager.py:689`). It computes no total.

For an empty list, the formatter says:

> No visually similar scans found.

There is no similarity threshold. An empty result instead means that the embedding matrix was empty, no scan was eligible, or metadata lookup failed to produce a result. It does not mean that indexed scans were evaluated and deemed insufficiently similar.

The database also returns each scan’s `content_type` (`db_manager.py:710`), but the formatter omits it. With `photographs_only=True`, an agent cannot tell whether an individual result was classified as `photograph` or `mixed`.

5. `keyword_search` can label unrelated opening text as “Match context”

Formatter: `rag.py:266`

Representative output:

> Matched in: original transcript (needle)  
> Match context: opening words with no query term

The FTS query searches the entire indexed field. The snippet builder searches only the first 1,000,000 raw characters for the corresponding occurrence. If it cannot locate one there, or its regular expression does not reproduce the FTS tokenizer’s match, it substitutes the field’s first approximately forty words (`db_manager.py:1046`, `db_manager.py:1085`).

The field attribution remains valid, but the displayed text may have no relationship to the occurrence. An agent could quote the opening text as surrounding evidence for the match.

6. `read_page_scans` silently ignores some invalid requested pages

Formatter and selection logic: `rag.py:784`

The code filters invalid page numbers out:

```python
selected_indices = [p - 1 for p in pages if 1 <= p <= total_pages]
```

It reports an error only when every requested number is invalid. For a ten-page document and `pages=[1, 999]`, the output would begin:

> Document 123: showing page(s) 1 of 10 total.

It does not say that page 999 was rejected. An agent would conclude that the request was handled as supplied or may overlook that it confused an archive page number with a sequential position.

7. Full-document retrieval omits searchable fields that it has already loaded

Formatter: `rag.py:453`

Both `get_document` and `get_document_by_item` use this formatter. The database result contains `summary`, `item_description`, `languages`, `item_id`, `source`, and other document columns (`db_manager.py:1469`). The formatter prints selected metadata and the two transcripts, but never prints those fields.

This matters because keyword search explicitly indexes summaries and item descriptions or photo captions. An agent following a keyword hit into `get_document` can see neither of those matching sources and may conclude that the reported match is unexplained or that the metadata is unavailable.

The label:

> Full original transcript (N chars):

also precedes only the first 8,000 characters. The formatter immediately provides an explicit truncation warning when needed, so this wording is contradictory but less likely to cause an unsupported absence claim.

8. `set_ui_language` reports a completed state change after only queuing a command

Direct formatter: `rag.py:918`

Output:

> Interface language switched to Polish.

At that point the tool has appended a command to an in-memory queue. The agent loop later converts it into an SSE event (`rag.py:1280`), and the browser changes its locale only if it receives and handles that event (`use-chat.ts:390`).

An agent would conclude that the interface state has already changed. The code knows only that it queued a request to change it.

## Formatter inventory

| Tool | Model-facing formatter | Result |
|---|---|---|
| `semantic_search` | `_format_semantic_results` | Finding 2 |
| `keyword_search` | `_format_keyword_results`, `_format_zero_hit_hint` | Finding 5 |
| `date_range_search` | `_format_date_range_results` | Finding 3 |
| `get_document` | `_format_document_detail` | Finding 7 |
| `get_document_by_item` | `_format_document_detail` | Finding 7 |
| `find_in_document` | `_format_find_in_document` | Finding 1 |
| `read_page_scans` | Inline text and multimodal blocks | Finding 6 |
| `visual_search` | `_format_visual_results` | Finding 4 |
| `browse_collection` | `_format_folder_list` | No discrepancy found |
| `browse_folder` | `_format_item_list` | No discrepancy found |
| `set_ui_language` | Direct return strings | Finding 8 |

`_format_collections_overview` was excluded because it formats database state into the system prompt, not a tool result. No files were changed.
