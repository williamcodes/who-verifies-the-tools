#!/usr/bin/env python3
"""Deterministic output-contract checker for the case manifest.

Usage:

    python3 contract_checker.py

No AI anywhere in this file: every check is a plain rule over the rendering
text plus the case's machine-readable input. The contract has four fields
(DESIGN.md, Section 5 of the paper): an output must disclose the SCOPE it
searched, its COMPLETENESS (a capped page must say so or give the true
total), the UNCERTAINTY status of derived values (an estimate must be
labeled), and the PROVENANCE namespace of identifiers.

Expected result on the frozen manifest: every condition-A rendering is
flagged, every condition-B rendering passes. That is a construction check,
not a discovery: A and B were built to differ exactly in these disclosures.
The paper reports it as "a checker of this form detects all 40 seeded
violations with no false positives on the 40 disclosed renderings", plus
the checker's limits (it verifies that a disclosure is PRESENT, not that
it is TRUE, and it needs the tool's contract fields to be known).

Writes cases/checker_report.json and prints a summary.
"""

import json
import re
from pathlib import Path

HERE = Path(__file__).resolve().parent
MANIFEST = HERE.parent / "data" / "cases" / "manifest.json"
REPORT = HERE.parent / "data" / "cases" / "checker_report.json"

# A bracketed number with no namespace tag, e.g. [10471]. The tagged forms
# look like [doc:10471] or [scan:10471].
BARE_ID = re.compile(r"\[\d+\]")
# A page reference, e.g. "page 8 of 14".
PAGE_REF = re.compile(r"\bpage \d+ of \d+", re.IGNORECASE)


def check_f1(text, case):
    """Scope: a capped no-hit search must disclose the cap and must not
    claim the full text was searched."""
    violations = []
    capped = bool(case["input"].get("scan_capped"))
    if capped and "1,000,000 characters" not in text:
        violations.append(
            "scope: search was capped but the output does not disclose the cap"
        )
    if capped and "FULL text" in text:
        violations.append(
            "scope: search was capped but the output claims the FULL text was searched"
        )
    return violations


def check_f2(text, case):
    """Completeness: a full result page must state the true total or say
    the page is capped, IN ITS HEADER; 'Found 20 document(s)' alone
    presents the page as the count. Only the header line is checked: the
    total's digits can appear coincidentally anywhere in twenty document
    rows (dates, identifiers, summaries), and a disclosure buried there
    would not license anything."""
    violations = []
    shown = len(case["input"])
    total = case["facts"]["true_total"]
    header = text.splitlines()[0]
    if shown == case["facts"]["page_limit"] and total > shown:
        has_total = f"of {total} documents" in header.replace(",", "")
        says_capped = "more documents match" in header or "not exhaustive" in header
        if not has_total and not says_capped:
            violations.append(
                f"completeness: {total} documents match but "
                f"the header presents the {shown}-result page "
                "with no total and no cap disclosure"
            )
    return violations


def check_f3(text, case):
    """Uncertainty: every page number derived by estimation must be labeled
    as an estimate."""
    violations = []
    for match in PAGE_REF.finditer(text):
        # Look just before the page reference for the estimate label.
        preceding = text[max(0, match.start() - 20) : match.start()]
        if "ESTIMATED" not in preceding:
            violations.append(
                f"uncertainty: '{match.group(0)}' is a "
                "proportional estimate presented without an "
                "estimate label"
            )
    return violations


def check_f4(text, case):
    """Provenance: every identifier must carry its namespace tag."""
    violations = []
    bare = BARE_ID.findall(text)
    if bare:
        shown = ", ".join(bare[:3])
        violations.append(
            f"provenance: {len(bare)} bracketed identifier(s) "
            f"without a namespace tag (e.g. {shown})"
        )
    return violations


CHECKS = {"F1": check_f1, "F2": check_f2, "F3": check_f3, "F4": check_f4}


def build_report(manifest):
    """Check every paired rendering and return the frozen report schema."""
    results = []
    flagged = {"a": 0, "b": 0}
    total = {"a": 0, "b": 0}

    for case in manifest["cases"]:
        check = CHECKS[case["family"]]
        for cond in ("a", "b"):
            violations = check(case[f"rendering_{cond}"], case)
            total[cond] += 1
            if violations:
                flagged[cond] += 1
            results.append(
                {
                    "case_id": case["case_id"],
                    "family": case["family"],
                    "cond": cond,
                    "violations": violations,
                }
            )

    report = {
        "manifest_built": manifest["built_utc"],
        "renderings_checked": total["a"] + total["b"],
        "condition_a_flagged": f"{flagged['a']}/{total['a']}",
        "condition_b_flagged": f"{flagged['b']}/{total['b']}",
        "results": results,
    }
    return report


def main():
    report = build_report(json.loads(MANIFEST.read_text()))
    REPORT.write_text(json.dumps(report, ensure_ascii=False, indent=2))

    print(
        f"A flagged: {report['condition_a_flagged']}  "
        f"B flagged: {report['condition_b_flagged']}"
    )
    for r in report["results"]:
        if r["cond"] == "b" and r["violations"]:
            print(f"  UNEXPECTED B violation {r['case_id']}: {r['violations']}")
    for r in report["results"]:
        if r["cond"] == "a" and not r["violations"]:
            print(f"  UNEXPECTED A pass {r['case_id']}")
    print(f"report: {REPORT}")


if __name__ == "__main__":
    main()
