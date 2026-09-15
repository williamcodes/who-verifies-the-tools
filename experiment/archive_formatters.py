"""Archive formatter functions copied verbatim from rag.py at 8364f22.

Only their standard-library dependency closure is included. See docs/verification.md.
"""

from typing import Dict, List

_FTS_FIELD_LABELS = {
    "title": "title",
    "original_transcript": "original transcript",
    "english_transcript": "English translation",
    "summary": "summary",
    "persons": "persons (catalog metadata)",
    "places": "places (catalog metadata)",
    "item_description": "item description / photo captions",
}


def find_document_scans(doc_id: int, db_manager) -> List[str]:
    """Find scan images for a document via the scans table."""
    return db_manager.get_document_scans(doc_id)


def enrich_documents_with_file_info(documents: List[Dict], db_manager=None) -> List[Dict]:
    """Add image paths and full content (transcript, translation, summary) to documents."""
    enriched = []
    for doc in documents:
        enriched_doc = doc.copy()
        doc_id = doc.get("id")
        if doc_id and db_manager:
            full_doc = db_manager.get_document(doc_id)
            if full_doc:
                for key in ("original_transcript", "english_transcript", "summary",
                            "persons", "places", "dates", "item_type", "item_author",
                            "document_url", "item_description", "languages"):
                    if key not in enriched_doc or not enriched_doc[key]:
                        enriched_doc[key] = full_doc.get(key)
            image_paths = find_document_scans(doc_id, db_manager)
            enriched_doc["image_paths"] = image_paths
            enriched_doc["has_images"] = len(image_paths) > 0
        else:
            enriched_doc["image_paths"] = []
            enriched_doc["has_images"] = False
        enriched.append(enriched_doc)
    return enriched


def _format_find_in_document(res: Dict, document_id: int, term: str) -> str:
    """Build text for an in-document term search.

    Absence wording is deliberately scoped: the strongest claim a transcript
    search licenses is "absent from the TRANSCRIPT" — only visual review can
    speak for the original document. When the scan cap truncated the search,
    the no-hit branch says so and withholds even that license: a capped scan
    cannot claim the FULL text was searched (the cap disclosure used to be
    appended only to FOUND results, so a capped no-hit read as an exhaustive
    absence — the exact overclaim this formatter exists to prevent). Page
    numbers are relayed as loud ESTIMATES so the agent cannot launder them
    into confirmed citations.
    """
    if not res:
        return f"Document {document_id} not found."

    if not res.get("found"):
        quality = res.get("transcript_quality") or "unrated"
        if res.get("scan_capped"):
            return (
                f'No occurrence of "{term}" in the SEARCHED PORTION of document '
                f"[doc:{document_id}]. This document's text exceeds the scan cap: "
                "only the first 1,000,000 characters of each field were searched, "
                f"and the original transcript is {res.get('transcript_chars', 0)} "
                f"chars in total. Transcript quality: {quality}. The term may still "
                "occur in the UNSEARCHED remainder — do NOT tell the user it is "
                "absent from the transcript or the document. Only reviewing the "
                "page images (read_page_scans) can confirm absence."
            )
        return (
            f'No occurrence of "{term}" in document [doc:{document_id}]. Searched the '
            f"FULL text: original transcript ({res.get('transcript_chars', 0)} chars), "
            "English translation, title, summary, persons/places metadata, and photo "
            f"captions. Transcript quality: {quality}. You may tell the user the term "
            "does not appear in the document's TRANSCRIPT; only reviewing the page "
            "images (read_page_scans) can confirm it is absent from the original "
            "document itself."
        )

    listed = res.get("matches", [])
    header = (f'Found {res["total_matches"]} occurrence(s) of "{term}" in document '
              f"[doc:{document_id}]")
    if res["total_matches"] > len(listed):
        header += f" (listing the first {len(listed)})"
    lines = [header, ""]
    for m in listed:
        field_label = _FTS_FIELD_LABELS.get(m["field"], m["field"])
        loc = f"{field_label} — {m['pct']}% through, character offset {m['offset']}"
        if m.get("est_page"):
            arch = (f", archive page {m['est_archive_page']}"
                    if m.get("est_archive_page") else "")
            loc += (f"; ESTIMATED page {m['est_page']} of {res['n_pages']}{arch} "
                    "(proportional estimate, NOT a confirmed page — verify with "
                    "read_page_scans before citing a page number)")
            if m.get("est_scan_url"):
                loc += (f". Direct image link for the estimated page: "
                        f"{m['est_scan_url']}")
        lines.append(f"- {loc}:")
        lines.append(f"  {m['context']}")
    if res.get("scan_capped"):
        lines.append("")
        lines.append("Note: this document's text exceeds the scan cap; only the first "
                     "1,000,000 characters of each field were searched.")
    quality = res.get("transcript_quality")
    if quality in ("partial", "garbled"):
        lines.append("")
        lines.append(f"⚠ Transcript quality: {quality.upper()} — review images to verify.")
    return "\n".join(lines)


def _format_date_range_results(documents: List[Dict], year_from: int, year_to: int) -> str:
    """Build text for a date range search tool result.

    The header reports the TRUE match total, not the page size, mirroring
    _format_keyword_results: a LIMITed page headed "Found 20 document(s)"
    reads as the whole result set when thousands may match the range.
    """
    if not documents:
        return f"No documents found in the date range {year_from}-{year_to}."

    total = documents[0].get("total_matches", len(documents))
    shown = len(documents)
    if total > shown:
        lines = [
            f"Showing the first {shown} of {total} documents with dates in "
            f"{year_from}-{year_to} (ordered by earliest year). "
            f"{total - shown} more documents match but are NOT listed — this page "
            "is not exhaustive: never present it as everything the archive holds "
            "for this period, and never report absence because something was not "
            "in the shown page. Narrow the year range to see the rest.\n"
        ]
    else:
        lines = [f"Found {shown} document(s) from {year_from}-{year_to}:\n"]
    for doc in documents:
        doc_id = doc.get("id", "?")
        title = doc.get("title", f"Document {doc_id}")
        date = doc.get("document_date") or doc.get("dates") or ""
        lines.append(f"[doc:{doc_id}] {title}")
        if date:
            lines.append(f"  Date: {date}")
        quality = doc.get("transcript_quality")
        if quality in ("partial", "garbled"):
            lines.append(f"  ⚠ Transcript quality: {quality.upper()} — review images to verify")
        image_paths = doc.get("image_paths", [])
        if image_paths:
            lines.append(f"  {len(image_paths)} page scan(s) — use read_page_scans to review originals")
        summary = doc.get("summary") or ""
        if summary:
            preview = summary[:200] + "..." if len(summary) > 200 else summary
            lines.append(f"  Summary: {preview}")
        lines.append("")

    return "\n".join(lines)


def _format_document_detail(doc: Dict, db_manager=None) -> str:
    """Build text for a full document retrieval."""
    if not doc:
        return "Document not found."

    doc_id = doc.get("id", "?")
    title = doc.get("title", f"Document {doc_id}")

    text = f"Document [doc:{doc_id}]: {title}\n"
    if doc.get("dates"):
        text += f"Date: {doc['dates']}\n"
    elif doc.get("document_date"):
        text += f"Date: {doc['document_date']}\n"
    if doc.get("author") or doc.get("item_author"):
        text += f"Author: {doc.get('author') or doc.get('item_author')}\n"
    if doc.get("item_type"):
        text += f"Type: {doc['item_type']}\n"
    if doc.get("persons"):
        text += f"Persons: {doc['persons']}\n"
    if doc.get("places"):
        text += f"Places: {doc['places']}\n"
    if doc.get("document_url"):
        text += f"Archive URL: {doc['document_url']}\n"

    quality = doc.get("transcript_quality")
    if quality in ("partial", "garbled"):
        text += f"⚠ Transcript rated {quality.upper()} — may contain garbled or incomplete text. Review images with read_page_scans to verify.\n"

    image_paths = doc.get("image_paths", [])
    if not image_paths and db_manager:
        image_paths = find_document_scans(doc_id, db_manager)
    if image_paths:
        text += f"This document has {len(image_paths)} page scan(s). Use read_page_scans to review the original scans.\n"

    transcript = doc.get("original_transcript") or ""
    if transcript:
        truncated = transcript[:8000]
        text += f"\nFull original transcript ({len(transcript)} chars):\n{truncated}"
        if len(transcript) > 8000:
            text += (f"\n... [display truncated — {len(transcript) - 8000} more characters not shown; "
                     "a keyword match may fall in the hidden portion — locate it with "
                     "find_in_document; never conclude a term is absent from this excerpt]")

    english = doc.get("english_transcript") or ""
    if english:
        truncated = english[:8000]
        text += f"\n\nEnglish translation ({len(english)} chars):\n{truncated}"
        if len(english) > 8000:
            text += (f"\n... [display truncated — {len(english) - 8000} more characters not shown; "
                     "a keyword match may fall in the hidden portion — locate it with "
                     "find_in_document; never conclude a term is absent from this excerpt]")

    return text
