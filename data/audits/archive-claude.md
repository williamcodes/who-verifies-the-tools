I have everything I need. No production logs or traces exist in this snapshot (no `*.db`, no LangSmith export, no `*.jsonl`), so I built a fixture database and drove the real tool functions from `create_tools` unmodified, stubbing only the langchain imports. Every quoted output below is actual harness output.

## Inventory: model-facing formatters

| # | Formatter | Location | Feeds |
|---|---|---|---|
| 1 | `_format_semantic_results` | rag.py:170 | `semantic_search` |
| 2 | `_format_keyword_results` | rag.py:226 | `keyword_search` |
| 3 | `_format_zero_hit_hint` | rag.py:279 | `keyword_search` (zero-hit suffix) |
| 4 | `_format_find_in_document` | rag.py:348 | `find_in_document` |
| 5 | `_format_date_range_results` | rag.py:402 | `date_range_search` |
| 6 | `_format_visual_results` | rag.py:430 | `visual_search` |
| 7 | `_format_document_detail` | rag.py:453 | `get_document`, `get_document_by_item` |
| 8 | `_format_folder_list` | rag.py:555 | `browse_collection` |
| 9 | `_format_item_list` | rag.py:582 | `browse_folder` |
| 10 | inline content-block builder | rag.py:771–845 | `read_page_scans` |
| 11 | inline return | rag.py:920 | `set_ui_language` |
| 12 | `_format_collections_overview` | rag.py:515 | system prompt |
| 13 | `_build_snippet` | db_manager.py:1046 | supplies `Match context:` for #2 |
| 14 | `collected_findings` re-render | rag.py:1251, 1109 | partial-answer synthesizer |

`_humanize_tool_start` / `_humanize_tool_step` (rag.py:1026, 1046) render SSE progress text for the browser only and never reach the model. Clear.

Thirteen findings follow, most severe first.

---

## F1. `find_in_document` says it searched the FULL text after a 1,000,000-char cap truncated it, and licenses an absence claim

**Formatter:** rag.py:359–368 (the `if not res.get("found")` branch)

**Output** (harness, doc with a 1,026,547-char transcript, term at offset 1,020,024):

> `No occurrence of "Kowalski" in document [doc:1]. Searched the FULL text: original transcript (1026547 chars), English translation, title, summary, persons/places metadata, and photo captions. Transcript quality: unrated. You may tell the user the term does not appear in the document's TRANSCRIPT; only reviewing the page images (read_page_scans) can confirm it is absent from the original document itself.`

**What the code did:** `db_manager.find_in_document` truncates every field at `_SNIPPET_SCAN_CAP` = 1,000,000 chars (db_manager.py:1162–1165) and sets `scan_capped = True`. It searched the first 1,000,000 characters. The term is present at 1,020,024. The returned dict carries `scan_capped: True`, and `_format_find_in_document` does surface it, but only at rag.py:388 in the *found* branch. The not-found branch returns at line 360 and never reads the flag.

Worse, `transcript_chars` (db_manager.py:1208) is `len(original_transcript)`, the full length. So the output prints the full 1,026,547 next to the words "Searched the FULL text," and that number corroborates the false completeness claim.

**What the agent concludes:** that the term is absent from the transcript. The output tells it so in as many words. The transcript contains the term.

## F2. `Match context:` shows the opening of the field when the snippet scanner never located the match

**Formatter:** rag.py:262 (`lines.append(f"  Match context: {snippet}")`), fed by `_build_snippet` at db_manager.py:1087

**Output** (same document, `keyword_search(["Kowalski"])`):

> `[doc:1] Ksiega pamiatkowa`
> `  Matched in: original transcript (Kowalski)`
> `  Match context: Rozdzial pierwszy o sprawach ogolnych. Rozdzial pierwszy o sprawach ogolnych. Rozdzial pierwszy o sprawach ogolnych. Rozdzial pierwszy o sprawach ogolnych. ...`

**What the code did:** `_search_folded` stops at the same 1,000,000-char cap (db_manager.py:1016) and returns `None`. `_build_snippet` then falls through to `return " ".join(raw.split()[:self._SNIPPET_FALLBACK_WORDS])`, the first 40 words of the field. The label still reads "Match context." Nothing in the output distinguishes a located match from the fallback except the absence of `**` bolding, which the agent has no rule for.

**What the agent concludes:** that "Kowalski" appears in or near this passage about general administrative matters. It appears 1.02 million characters later.

**F1 and F2 chain.** The system prompt (rag.py:60) instructs: *"if you cannot find the term in the displayed text, locate it with find_in_document, never guess that the match came from somewhere else, and NEVER retract a reported match merely because the displayed excerpt does not show it."* An agent that follows that instruction exactly reaches F1, which tells it the term is not there. The two tools contradict each other and the second one supplies the license to retract. `test_find_in_document.py:5` records that this repo already shipped a session where an agent retracted a true search hit; this path reproduces it on long documents.

## F3. `date_range_search` reports the page size as the total, and the page is the 20 earliest documents

**Formatter:** rag.py:407 — `lines = [f"Found {len(documents)} document(s) from {year_from}-{year_to}:\n"]`

**Output** (fixture with 60 documents genuinely dated 1918–1939):

> `Found 20 document(s) from 1918-1939:`
> `[doc:22] Raport sytuacyjny 22 / Date: 1918-03-01` … `[doc:25] …`
>
> `>>> docs the SQL candidate query actually matched: 60`
> `>>> years shown in the 20 results: ['1918', '1919', '1920', '1921', '1922', '1923', '1924']`
> `>>> years present in the full range: ['1918' … '1939']`

**What the code did:** `db_manager.date_range_search` (db_manager.py:1419–1452) runs a SQL query with **no LIMIT**, calls `cursor.fetchall()`, then post-filters in Python and `break`s once `len(results) >= limit` (20, set at rag.py:713). All 60 matching rows are in memory when it stops. The code has the true total and discards it. Ordering is `ORDER BY d.date_year_min ASC`, so the 20 kept are the earliest, not the most relevant.

This is the exact defect `_format_keyword_results` was fixed for. Its own docstring (rag.py:230–233) says: *"Before this, a LIMITed page was headed 'Found 10 document(s)', and a reader treating that as the whole result set concluded absence from it."* `date_range_search` still does that.

**What the agent concludes:** two errors. That the archive holds 20 documents from 1918–1939, and that it holds nothing after 1924. The system prompt's caveat ("Returns at most 20 results") is contradicted by the formatter's own header, and says nothing about the date-ascending bias.

## F4. `semantic_search` retrieves five documents and shows three, with no count of either

**Formatter:** rag.py:170 (`max_docs: int = 3`), called without an override at rag.py:655

**Output:**

> `Document [doc:30]: Raport sytuacyjny 30 (similarity: 1.00)` … `Document [doc:29]` … `Document [doc:2]` …
>
> `>>> registry now holds doc ids: [2, 3, 4, 29, 30]`

**What the code did:** rag.py:650 requests `limit=5`. All five are enriched with a full DB round trip each (rag.py:651) and registered in `document_registry` as citable (rag.py:652–654). Then `_format_semantic_results` slices `documents[:3]`. Documents 3 and 4 were fetched, paid for, and made citable, and the agent is never told they exist.

The output carries no header at all: no count, no "showing 3 of 5," no statement of what was searched. Neither the tool docstring (rag.py:646–648) nor the system prompt mentions any cap.

**What the agent concludes:** that the semantic index returned three documents for this query. It cannot tell whether three is the cap, the eligible total, or the whole archive's holdings on the topic. The system prompt tells it to treat low scores as evidence that "no strong match exists," so a three-item low-scoring page reads as a searched-and-empty archive.

## F5. The partial-answer synthesizer cuts each tool result at 4,000 chars, removing the truncation warnings

**Formatter:** rag.py:1251 — `collected_findings.append(f"[{chunk.name or 'tool'}] {str(chunk.content)[:4000]}")`, consumed at rag.py:1109 `findings_blob = "\n\n".join(collected_findings)[:60000]`

**Output** (harness, `get_document` on a 24,000-char transcript):

> `get_document output length: 16572`
> TAIL of the real tool output: `… Rozkaz. Rozkaz.  ... [display truncated — 16000 more characters not shown; a keyword match may fall in the hidden portion — locate it with find_in_document; never conclude a term is absent from this excerpt]`
> TAIL of what the synthesizer reads: `… Rozkaz. Rozkaz. Rozkaz. Rozkaz. Rozkaz.`
> `>>> guard-rail text present in synthesizer input?: False`

**What the code did:** `_format_document_detail` appends its truncation warning at the *end* of the string (rag.py:492–495, 501–504). The 4,000-char slice keeps the head and throws away the tail, so the warning is always the first thing lost. A second silent cut at 60,000 chars follows. The synthesizer's prompt then says: *"Using ONLY the findings gathered so far below, write the best partial answer you can … and be explicit about what remains uncertain or unsearched."*

**What the agent concludes:** that it has read the document. It is asked to flag what is unsearched while holding text that was cut twice with no marker. The `keyword_search` "not exhaustive" header survives (it is at the head), but every `get_document` guard rail is stripped from exactly the code path built to handle degraded evidence.

`str(chunk.content)` also applies to `read_page_scans`, which returns a list of content blocks. The 4,000-char window there is consumed by the Python `repr` of base64 image data.

## F6. `transcript_quality` is a Gemini Flash rating of the first 500 characters, presented as a property of the whole transcript

**Formatters:** rag.py:192–195, 264, 415–416, 480–481 (four sites)

**Output:**

> `⚠ Transcript quality: PARTIAL — review images with read_page_scans to verify content`
> `⚠ Transcript rated GARBLED — may contain garbled or incomplete text.`

**What the code did:** `pipeline/audit_transcripts.py:42` sets `SNIPPET_LENGTH = 500` and line 101 passes `text[:SNIPPET_LENGTH]` to `gemini-3-flash-preview`. The rating describes the first 500 characters and nothing else.

Two consequences. A "good" rating on a 200,000-char transcript means one opening paragraph looked clean to a small model, and it suppresses the warning for the other 199,500 characters. And the unrated case (NULL) produces no output at all in three of the four formatters, because they only branch on `quality in ("partial", "garbled")`. Only `_format_find_in_document` prints `Transcript quality: unrated`.

**What the agent concludes:** that an unaudited document and an audited-clean document are the same thing, and that a whole transcript has been quality-checked. The system prompt reinforces this at rag.py:83: *"Documents with partial or garbled transcript quality: Always pull images. These transcripts have been flagged by automated quality audit as unreliable."* By implication, no flag means checked and fine. Neither is what the code knows.

## F7. "English translation (N chars)" is a machine translation of at most the first 8,000 Polish characters

**Formatter:** rag.py:499 — `text += f"\n\nEnglish translation ({len(english)} chars):\n{truncated}"`

**What the code did:** `pipeline/generate_summaries_translations.py:87–90` calls the model with `f"{state['text'][:8000]}"` and `max_tokens=4000`. The English field covers the document's first 8,000 Polish characters, and the output cap can cut it shorter still. `rag.translate_document` (rag.py:1341) uses a 30,000-char input cap for the on-demand path, a different number for the same field.

The formatter reports `len(english)` as a plain character count beside "English translation." For a 60,000-char Polish document, the English side is typically well under 8,000 chars, so the display-truncation notice at rag.py:501 never fires and the translation looks complete.

**What the agent concludes:** that it holds an English rendering of the document. It holds one of the opening 13%. This also weakens F1's claim to have searched the "English translation": for any document over 8,000 chars, that field was never capable of containing later material.

## F8. `Transcript excerpt:` may be an LLM-generated summary

**Formatter:** rag.py:200–208

**Output** (document with empty transcripts and only a generated summary):

> `Document [doc:2]: Fotografia grupowa (similarity: 0.71)`
> `  Persons: Pilsudski, Jozef`
> `Transcript excerpt:`
> `A group photograph showing officers at a ceremony; no legible text is present on the print.`

**What the code did:** rag.py:201–205 selects `original_transcript or english_transcript or summary` and labels all three "Transcript excerpt." The third is a 3-5 sentence Claude summary of the first 8,000 chars (`generate_summaries_translations.py:57`). `Searcher.search` (searcher.py:47–52) adds a fourth provenance by backfilling `summary` from the first 500 chars of the English translation when it is empty.

**What the agent concludes:** that this is source text from the document, and cites `[doc:2]` for it. It is a model's paraphrase, or a translation, or the original Polish, with nothing in the output to tell which.

## F9. `visual_search` silently drops unclassified scans, and "Found N visually similar" is a top-k slice

**Formatter:** rag.py:435 — `lines = [f"Found {len(scans)} visually similar page scan(s):"]`

**Output** (fixture: 6 scans with embeddings, 1 classified):

> `Found 1 visually similar page scan(s):`
> `- [scan:1] Raport 1 (Maszynopis) — page 1 (archive page 110), document [doc:1], similarity 1.00`
> `>>> total scans with embeddings: 6 | classified: 1`

**What the code did:** with `photographs_only=True`, rag.py:868 passes `content_types=["photograph", "mixed"]`, and `search_similar_scans` builds the eligible set with an inner `JOIN scan_classifications` (db_manager.py:673–678). A scan that was never run through `pipeline/classify_scans.py` is excluded exactly like a scan classified as a document. The docstring at db_manager.py:653 states this ("unclassified scans are excluded") and the formatter never does. Scans whose item has no `documents` row are dropped too (db_manager.py:670).

Separately, the search is brute-force cosine over the top `limit=12` (rag.py:869) with no similarity threshold, so whenever 12 eligible scans exist the output always says "Found 12 visually similar page scan(s)" regardless of relevance. The system prompt warns that `semantic_search` "always returns results regardless of relevance" and gives no such warning for `visual_search`.

**What the agent concludes:** that the archive contains one matching photograph. The code cannot distinguish "not a photograph" from "never classified," and neither can the agent from this output. I cannot verify the unclassified share in production from this snapshot; the disclosure gap holds whatever that share is.

## F10. `read_page_scans` silently discards out-of-range page requests when at least one page is valid

**Formatter:** rag.py:785, 795–806

**Output** (`read_page_scans(document_id=1, pages=[1, 118])`, document has 4 scans):

> `Document 1: showing page(s) 1 of 4 total. Each image below is preceded by a label with its sequential position, its ARCHIVE page number …`

**What the code did:** rag.py:785 filters with `[p - 1 for p in pages if 1 <= p <= total_pages]`, dropping 118. The code handles the all-invalid case well (rag.py:787–792 returns a pointed error naming the archive-page confusion), but the mixed case falls through and the header reports only what survived. Page 118 vanishes without a word.

This is the confusion the tool was hardened against everywhere else. The document's own archive page labels here run 110–113, and `find_in_document` hands the agent `archive page 110` and a `est_scan_url` containing `-110.jpg`. An agent that carries one of those numbers into `pages` gets a plausible-looking result for the pages that happened to be in range.

**What the agent concludes:** that its request was served. It examined page 1 and believes it also examined page 118.

## F11. `get_document_by_item` asserts the item exists when it may not

**Formatter:** rag.py:743

**Output** (item_id 9999, which is not in the `items` table at all):

> `No document found for item 9999. This item may not have been transcribed.`
> `>>> rows in items with item_id=9999: 0`

**What the code did:** `db_manager.get_document_by_item` runs one `SELECT … WHERE d.item_id = ?` and returns `{}` on no row. It never queries `items`, so it cannot tell a nonexistent item from a real item with no document. The message picks one and states it.

**What the agent concludes:** that item 9999 is a real archival item that has not been transcribed, which is a reportable fact about the archive's holdings. The system prompt warns twice that `item_id` and `document_id` are different numbering systems, so a mistyped or mistakenly-reused ID is the likely way to reach this line, and this is the branch that reassures the agent the ID was good.

## F12. `set_ui_language` reports a completed switch for a queued request

**Formatter:** rag.py:918–920

**Output:**

> `Interface language switched to Polish.`
> `>>> ui_commands queue: [{'action': 'set_language', 'locale': 'pl'}]`

**What the code did:** appended a dict to an in-process list. The command is drained into an SSE event later, at rag.py:1281–1282, and the frontend acts on it at `frontend/src/hooks/use-chat.ts:394`. Nothing has switched at the moment the model reads the sentence.

**What the agent concludes:** that the interface is now Polish, and tells the user so. If the stream errors or the client disconnects between rag.py:920 and rag.py:1282, the model has already asserted a UI change that never happened.

## F13. `Persons` and `Places` are labeled catalog metadata in one formatter and left bare in three

**Formatters:** labeled at rag.py:219–220 (`_FTS_FIELD_LABELS`: `"persons (catalog metadata)"`); bare at rag.py:188–189 (`_format_semantic_results`), rag.py:471–472 (`_format_document_detail`), rag.py:602–604 (`_format_item_list`)

**Output:**

> `  Persons: Pilsudski, Jozef`

**What the code did:** all four read the same `items.persons` column. The system prompt (rag.py:96–98) is explicit that this field "records who an ITEM concerns. It is item-level, not frame-level … and it can be wrong (e.g., a landscape or building tagged with a person who is not in it)."

**What the agent concludes:** in the `keyword_search` path, correctly, that the name came from the catalog. In the `get_document`, `semantic_search`, and `browse_folder` paths, that the document names this person. The prompt's attribution rules ("catalogued as showing X," not "this photo shows X") are scoped to photographs, so an agent reading `Persons:` under a `get_document` result for a text query has no cue to attribute rather than assert.

---

## Checked and clear

`_format_keyword_results` reports the true `total_matches` with an explicit non-exhaustiveness warning, and `db_manager.keyword_search` runs a real `COUNT` when the page comes back full. `_format_zero_hit_hint` correctly separates AND-combination failure from a missing term and refuses to let the agent call the first a spelling correction. `_format_find_in_document`'s *found* branch labels page numbers as estimates loudly and discloses both the 20-match listing cap and `scan_capped`. `browse_collection` and `browse_folder` run unlimited queries, so their "Found N" headers are true totals. `_format_collections_overview` distinguishes indexed, not-yet-indexed, and not-digitized. `read_page_scans` discloses its 10-page cap and labels each image with sequential position, archive page, and link.

I also checked whether one item's scans could be over-attributed across several documents. `documents.item_id` has a non-unique index, so the DB permits it, but both ingest paths guard against it (`pipeline/ingest_series.py:331` `NOT EXISTS`, `pipeline/transcribe_scans.py:376` `if existing`). Not a finding.

Nothing was changed. The harness and stubs live in `<local-path>/audit` and touch no repository file.
