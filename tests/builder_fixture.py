"""Synthetic SQLite rows and tool results for builder equivalence tests.

These inputs exercise the historical selection code without an archive database.
They are test data, not reconstructed historical records.
"""

import copy
import sqlite3
from datetime import datetime, timezone


class FixedClock:
    @classmethod
    def now(cls, tz=None):
        return datetime(2026, 8, 25, 21, 36, 13, tzinfo=timezone.utc)


class ArchiveFixture:
    def __init__(self):
        self.conn = sqlite3.connect(":memory:")
        self.conn.executescript("""
            CREATE TABLE documents (id INTEGER, item_id INTEGER);
            CREATE TABLE document_content (document_id INTEGER, original_transcript TEXT,
                                           english_transcript TEXT);
            CREATE TABLE items (item_id INTEGER, document_url TEXT);
            CREATE TABLE scans (scan_id INTEGER, item_id INTEGER, sequence_order INTEGER);
        """)
        self.docs = {}
        self.find_results = {}
        self.date_rows = {}
        self.repro = {
            "r6_false_absence_examples": {"per_document": []},
            "r2_capped_transcripts": {"documents": []},
            "r4_date_aggregates": {"years_over_20": {}},
            "r5_id_substitution": {"same_item_document_ids": [1001, 1002]},
        }
        # F1: seven capped documents, two candidate terms each. Unequal
        # lengths make the final three picks sensitive to the ranking rule.
        for i in range(7):
            doc_id = 90001 + i
            terms = [f"term{i}first", f"term{i}second"]
            text = "x" * 1_000_001 + " " + " ".join(terms) + " " * (i * 20)
            self.add_document(doc_id, text)
            entries = []
            for term in terms:
                entries.append({"term": term, "field": "original_transcript",
                                "sqlite_instr_position": text.index(term) + 1})
                self.find_results[doc_id, term] = {
                    "found": False, "scan_capped": True,
                    "transcript_chars": len(text), "transcript_quality": "good",
                }
            self.repro["r6_false_absence_examples"]["per_document"].append(
                {"document_id": doc_id, "false_absence_terms": entries})
            self.repro["r2_capped_transcripts"]["documents"].append(
                {"document_id": doc_id, "original_transcript_chars": len(text),
                 "english_transcript_chars": 0})
        # F2: 90 years, distinct totals, 20 rows per page, with images and
        # a long summary to exercise enrichment and preview truncation.
        for year in range(1850, 1940):
            total = 100 + (year * 7) % 91
            self.repro["r4_date_aggregates"]["years_over_20"][str(year)] = total
            rows = []
            for i in range(20):
                doc_id = year * 100 + i
                doc = {"id": doc_id, "title": f"Indexed record {i}",
                       "dates": str(year), "summary": "archival note " * 20,
                       "transcript_quality": "partial" if i == 0 else "good",
                       "total_matches": total}
                self.docs[doc_id] = doc
                rows.append(doc)
            self.date_rows[year] = rows
        # F3: skip the first eligible document (no new word past midpoint),
        # then select the first ten valid results from eleven candidates.
        for doc_id in range(1000, 1012):
            term = "witnesses"
            text = "x " * 6000 + (term if doc_id != 1000 else "x") + " x" * 5000
            self.add_document(doc_id, text)
            offset = 12000
            self.find_results[doc_id, term] = {
                "found": True, "scan_capped": False, "total_matches": 1,
                "n_pages": 4, "transcript_quality": "good",
                "matches": [{"field": "original_transcript", "pct": 50,
                             "offset": offset, "est_page": 3,
                             "est_archive_page": 149,
                             "est_scan_url": "https://example.org/scan/149",
                             "context": "the witnesses signed"}],
            }

    def add_document(self, doc_id, text):
        item = doc_id + 1000000
        self.conn.execute("INSERT INTO documents VALUES (?, ?)", (doc_id, item))
        self.conn.execute("INSERT INTO document_content VALUES (?, ?, '')", (doc_id, text))
        url = f"https://example.org/archive?handle=1/{doc_id}"
        self.conn.execute("INSERT INTO items VALUES (?, ?)", (item, url))
        for i in range(4):
            self.conn.execute("INSERT INTO scans VALUES (?, ?, ?)",
                              (doc_id * 1000 + i, item, i))
        # A bare document ID resolves to a different item's scan.
        collision_item = item if doc_id in (1001, 1002) else item + 100
        self.conn.execute("INSERT INTO scans VALUES (?, ?, 0)", (doc_id, collision_item))
        self.docs[doc_id] = {"id": doc_id, "title": "Fixture document",
                             "original_transcript": text,
                             "document_url": url, "dates": "1920"}

    def _get_conn(self):
        return self.conn

    def get_document(self, doc_id):
        return copy.deepcopy(self.docs.get(doc_id))

    def get_document_scans(self, doc_id):
        return [f"scans/{doc_id}-{i}.jpg" for i in range(4)]

    def find_in_document(self, doc_id, term):
        return copy.deepcopy(self.find_results[doc_id, term])

    def date_range_search(self, year_from, year_to, limit):
        assert year_from == year_to and limit == 20
        return copy.deepcopy(self.date_rows[year_from])

    def close(self):
        self.conn.close()


def build_all(builder, fixture):
    return (builder.build_f1(fixture, fixture.repro)
            + builder.build_f2(fixture, fixture.repro)
            + builder.build_f3(fixture, fixture.conn)
            + builder.build_f4(fixture, fixture.conn, fixture.repro))
