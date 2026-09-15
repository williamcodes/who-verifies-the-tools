#!/usr/bin/env python3
"""Reproduce the source database aggregates used to construct the cases.

Opens ../archive-downloader/archive.db strictly read-only (SQLite URI mode=ro)
and writes one JSON artifact per run to data/reproductions/.

Reproduced items, with their historical evidence identifiers:
  R2  count of documents with a transcript field longer than _SNIPPET_SCAN_CAP
  R3  canary positions: doc 2030 'Zmierzyłem', doc 18866 'biologicznym'
  R4  date aggregates: documents matching year 1920; years with > 20 matches
  R5  document-to-scan ID substitution audit
  R6  regenerated false-absence examples (terms only reachable past the cap)

The fold logic replicates fold_text/_fold_char/FOLD_MAP from
../archive-downloader/db_manager.py:75-127 so the absence check matches the
production snippet scanner without importing that module. R6 uses substring
absence on folded, lowercased text, which is stricter than the production
word-boundary regex: if a folded term never occurs as a substring in the first
1,000,000 characters of any searched field, find_in_document cannot match it
there under any tokenization.
"""

import json
import re
import sqlite3
import subprocess
import sys
import unicodedata
from datetime import UTC, datetime
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
SRC = REPO.parent / "archive-downloader"
DB = SRC / "archive.db"
OUT_DIR = REPO / "data" / "reproductions"
CAP = 1_000_000  # db_manager.py:951 _SNIPPET_SCAN_CAP

# --- fold_text replica (db_manager.py:75-127) ---
FOLD_MAP = {"ł": "l", "Ł": "L"}
_FOLD_TABLE = {}


def _fold_char(ch):
    if ch in FOLD_MAP:
        return FOLD_MAP[ch]
    decomp = unicodedata.normalize("NFD", ch)
    if (
        len(decomp) > 1
        and unicodedata.combining(decomp[0]) == 0
        and all(unicodedata.combining(c) for c in decomp[1:])
    ):
        return decomp[0]
    return ch


def fold_text(s):
    for ch in set(s):
        cp = ord(ch)
        if cp not in _FOLD_TABLE:
            _FOLD_TABLE[cp] = _fold_char(ch)
    return s.translate(_FOLD_TABLE)


assert fold_text("Gągała") == "Gagala"
assert fold_text("Zmierzyłem") == "Zmierzylem"
assert len(fold_text("łąśćżźęóń")) == len("łąśćżźęóń")


def norm(s):
    """Fold + casefold: the comparable form for absence checks."""
    return fold_text(s or "").casefold()


def git(*args):
    return subprocess.run(
        ["git", "-C", str(SRC), *args], capture_output=True, text=True, check=True
    ).stdout.strip()


def searched_fields(conn, doc_id):
    """The seven find_in_document text sources for one document.

    Mirrors db_manager.get_document + _snippet_source_text + _item_captions_text:
    title from documents; original_transcript, english_transcript, summary from
    document_content; persons, places from items; item_description is
    items.description plus concatenated scan captions.
    """
    row = conn.execute(
        """
        SELECT d.title, dc.original_transcript, dc.english_transcript,
               dc.summary, i.persons, i.places, i.description, d.item_id
        FROM documents d
        JOIN document_content dc ON d.id = dc.document_id
        LEFT JOIN items i ON d.item_id = i.item_id
        WHERE d.id = ?
        """,
        (doc_id,),
    ).fetchone()
    if row is None:
        return None
    title, ot, et, summary, persons, places, descr, item_id = row
    captions = ""
    if item_id is not None:
        cap_row = conn.execute(
            """
            SELECT GROUP_CONCAT(
                       TRIM(COALESCE(sc.caption, '') || ' ' || COALESCE(sc.legible_text, '')),
                       ' ')
            FROM scan_captions sc
            JOIN scans s ON s.scan_id = sc.scan_id
            WHERE s.item_id = ?
            """,
            (item_id,),
        ).fetchone()
        captions = (cap_row[0] or "") if cap_row else ""
    item_description = (
        ((descr or "") + " " + captions).strip() if captions else (descr or "")
    )
    return {
        "title": title or "",
        "original_transcript": ot or "",
        "english_transcript": et or "",
        "summary": summary or "",
        "persons": persons or "",
        "places": places or "",
        "item_description": item_description,
    }


WORD_RE = re.compile(r"[^\W\d_]{6,}", re.UNICODE)


def false_absence_terms(fields, max_terms=5):
    """Terms present past the cap in some field but absent (folded, casefolded,
    as substring) from the first CAP characters of every searched field."""
    haystacks = {name: norm(text[:CAP]) for name, text in fields.items()}
    found = []
    seen = set()
    for name, text in fields.items():
        if len(text) <= CAP:
            continue
        # Scan the WHOLE field and keep only words whose true start is at or
        # past the cap. Scanning text[CAP:] instead would create a false word
        # boundary at the cap: the tail of a word straddling position
        # 1,000,000 would pose as a whole word that the production
        # whole-token search could never match.
        for m in WORD_RE.finditer(text):
            if m.start() < CAP:
                continue
            word = m.group(0)
            key = norm(word)
            if key in seen:
                continue
            seen.add(key)
            if any(key in h for h in haystacks.values()):
                continue
            start = m.start()
            found.append(
                {
                    "term": word,
                    "field": name,
                    "offset_0based": start,
                    "sqlite_instr_position": start + 1,
                    "context": text[max(0, start - 60) : start + len(word) + 60],
                }
            )
            if len(found) >= max_terms:
                return found
    return found


def main():
    if not DB.exists():
        sys.exit(f"database not found: {DB}")
    conn = sqlite3.connect(f"file:{DB}?mode=ro", uri=True)

    result = {
        "run_utc": datetime.now(UTC).isoformat(timespec="seconds"),
        "database": str(DB),
        "source_commit": git("rev-parse", "HEAD"),
        "source_dirty": git("status", "--short") or "(clean)",
        "scan_cap": CAP,
    }

    # Denominators
    result["totals"] = {
        "documents": conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0],
        "document_content_rows": conn.execute(
            "SELECT COUNT(*) FROM document_content"
        ).fetchone()[0],
        "scans": conn.execute("SELECT COUNT(*) FROM scans").fetchone()[0],
    }

    # R2: documents with a transcript field beyond the snippet scan cap
    rows = conn.execute(
        """
        SELECT document_id,
               COALESCE(LENGTH(original_transcript), 0) AS ot_len,
               COALESCE(LENGTH(english_transcript), 0) AS et_len
        FROM document_content
        WHERE ot_len > :cap OR et_len > :cap
        ORDER BY document_id
        """,
        {"cap": CAP},
    ).fetchall()
    result["r2_capped_transcripts"] = {
        "count": len(rows),
        "documents": [
            {
                "document_id": r[0],
                "original_transcript_chars": r[1],
                "english_transcript_chars": r[2],
            }
            for r in rows
        ],
    }

    # R3: canary positions recorded in the August audit
    canaries = []
    for doc_id, field, term in (
        (2030, "original_transcript", "Zmierzyłem"),
        (18866, "english_transcript", "biologicznym"),
    ):
        pos, in_first_cap = conn.execute(
            f"""
            SELECT INSTR({field}, :term),
                   INSTR(SUBSTR({field}, 1, :cap), :term)
            FROM document_content WHERE document_id = :doc
            """,
            {"term": term, "cap": CAP, "doc": doc_id},
        ).fetchone()
        canaries.append(
            {
                "document_id": doc_id,
                "field": field,
                "term": term,
                "sqlite_instr_position": pos,
                "exact_match_in_first_cap": bool(in_first_cap),
            }
        )
    result["r3_canaries"] = canaries

    # R4: date aggregates, segment semantics from backfill_date_years /
    # date_range_search post-filter (db_manager.py:39-42, 1443-1450)
    year_counts = {}
    for _doc_id, date_str in conn.execute(
        "SELECT id, document_date FROM documents "
        "WHERE document_date IS NOT NULL AND document_date != ''"
    ):
        years = set()
        for segment in date_str.split("; "):
            segment = segment.strip()
            if len(segment) >= 4 and segment[:4].isdigit():
                years.add(int(segment[:4]))
        for y in years:
            year_counts[y] = year_counts.get(y, 0) + 1
    over_20 = {y: c for y, c in year_counts.items() if c > 20}
    result["r4_date_aggregates"] = {
        "documents_matching_1920": year_counts.get(1920, 0),
        "years_with_more_than_20_matches": len(over_20),
        "years_over_20": {str(y): c for y, c in sorted(over_20.items())},
        "tool_page_limit": 20,
    }

    # R5: document-to-scan ID substitution audit
    r5 = conn.execute(
        """
        SELECT
          COUNT(*) AS total_documents,
          SUM(CASE WHEN s.scan_id IS NULL THEN 1 ELSE 0 END) AS id_not_a_scan_id,
          SUM(CASE WHEN s.scan_id IS NOT NULL
                    AND d.item_id IS NOT NULL
                    AND s.item_id = d.item_id THEN 1 ELSE 0 END) AS scan_of_same_item,
          SUM(CASE WHEN s.scan_id IS NOT NULL
                    AND (d.item_id IS NULL OR s.item_id != d.item_id)
                   THEN 1 ELSE 0 END) AS scan_of_different_item
        FROM documents d
        LEFT JOIN scans s ON s.scan_id = d.id
        """
    ).fetchone()
    same_item_ids = [
        r[0]
        for r in conn.execute(
            """
            SELECT d.id FROM documents d
            JOIN scans s ON s.scan_id = d.id
            WHERE d.item_id IS NOT NULL AND s.item_id = d.item_id
            ORDER BY d.id
            """
        ).fetchall()
    ]
    not_scan_ids = [
        r[0]
        for r in conn.execute(
            """
            SELECT d.id FROM documents d
            LEFT JOIN scans s ON s.scan_id = d.id
            WHERE s.scan_id IS NULL ORDER BY d.id
            """
        ).fetchall()
    ]
    result["r5_id_substitution"] = {
        "total_documents": r5[0],
        "doc_id_is_not_a_scan_id": r5[1],
        "doc_id_is_scan_of_same_item": r5[2],
        "doc_id_is_scan_of_different_item": r5[3],
        "same_item_document_ids": same_item_ids,
        "not_a_scan_document_ids": not_scan_ids,
    }

    # R6: regenerate live false-absence examples for every capped document
    examples = []
    for doc in result["r2_capped_transcripts"]["documents"]:
        doc_id = doc["document_id"]
        fields = searched_fields(conn, doc_id)
        if fields is None:
            examples.append({"document_id": doc_id, "error": "document not found"})
            continue
        terms = false_absence_terms(fields)
        examples.append({"document_id": doc_id, "false_absence_terms": terms})
    result["r6_false_absence_examples"] = {
        "documents_with_at_least_one_term": sum(
            1 for e in examples if e.get("false_absence_terms")
        ),
        "per_document": examples,
    }

    conn.close()

    OUT_DIR.mkdir(parents=True, exist_ok=True)
    # Second-precision stamp, and mode "x" so a rerun can never silently
    # overwrite an earlier artifact.
    stamp = result["run_utc"].replace(":", "").replace("-", "")[:15]
    out_path = OUT_DIR / f"repro_{stamp}.json"
    with out_path.open("x") as f:
        f.write(json.dumps(result, ensure_ascii=False, indent=2))

    print(f"artifact: {out_path}")
    print(f"source commit: {result['source_commit']}")
    print(f"R2 capped transcripts: {result['r2_capped_transcripts']['count']}")
    for c in result["r3_canaries"]:
        print(
            f"R3 doc {c['document_id']} {c['term']!r}: instr={c['sqlite_instr_position']}"
            f" in_first_cap={c['exact_match_in_first_cap']}"
        )
    r4 = result["r4_date_aggregates"]
    print(
        f"R4 docs matching 1920: {r4['documents_matching_1920']}; "
        f"years >20 matches: {r4['years_with_more_than_20_matches']}"
    )
    r5d = result["r5_id_substitution"]
    print(
        f"R5 of {r5d['total_documents']} doc IDs: {r5d['doc_id_is_scan_of_different_item']} "
        f"resolve to a scan of a different item, {r5d['doc_id_is_scan_of_same_item']} to a "
        f"scan of the same item, {r5d['doc_id_is_not_a_scan_id']} are not scan IDs"
    )
    r6 = result["r6_false_absence_examples"]
    print(
        f"R6 documents with a live false-absence term: "
        f"{r6['documents_with_at_least_one_term']} of {len(r6['per_document'])}"
    )


if __name__ == "__main__":
    main()
