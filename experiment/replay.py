"""Offline reconstruction of frozen renderings, with byte-level checks.

F1/F2 preserve formatter inputs. F3/F4 preserve condition B and the deletion
transform that constructs A; they do not preserve all database inputs for B.
Replay validates those distinct contracts, then serializes historical metadata
unchanged. It never contacts the archive or claims to rerun its database queries.
"""

import copy
import hashlib
import json
import re
from collections import Counter
from pathlib import Path

if __package__:
    from . import build_manifest as builder, contract_checker
else:
    import build_manifest as builder
    import contract_checker

HERE = Path(__file__).resolve().parent
PROVENANCE = HERE / "provenance.json"
COUNTS = {"F1": 10, "F2": 10, "F3": 10, "F4": 10}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def validate_manifest(manifest):
    cases = manifest["cases"]
    if (
        dict(Counter(c["family"] for c in cases)) != COUNTS
        or manifest["counts"] != COUNTS
    ):
        raise ValueError("expected ten cases in each of F1, F2, F3, and F4")
    if len({c["case_id"] for c in cases}) != len(cases):
        raise ValueError("duplicate case IDs")
    for case in cases:
        if case["rendering_a"] == case["rendering_b"]:
            raise ValueError(f"{case['case_id']}: identical conditions")
        for condition in ("a", "b"):
            if (
                digest(case[f"rendering_{condition}"].encode())
                != case[f"sha256_{condition}"]
            ):
                raise ValueError(
                    f"{case['case_id']}: {condition} rendering hash mismatch"
                )


def reconstruct(manifest):
    """Recompute supported renderings, failing on any difference."""
    validate_manifest(manifest)
    result = copy.deepcopy(manifest)
    for case in result["cases"]:
        family = case["family"]
        if family == "F1":
            term = re.search(r'word "([^"]+)"', case["question"]).group(1)
            doc_id = int(case["case_id"].split("-")[1])
            case["rendering_a"] = builder.a_find(case["input"], doc_id, term)
            case["rendering_b"] = builder.b_find(case["input"], doc_id, term)
        elif family == "F2":
            year = int(case["case_id"].split("-")[1])
            case["rendering_a"] = builder.a_date(case["input"], year, year)
            case["rendering_b"] = builder.b_date(case["input"], year, year)
        else:
            transform = (
                builder.strip_estimates if family == "F3" else builder.strip_namespaces
            )
            if case["a_derivation"] != f"{transform.__name__}(rendering_b)":
                raise ValueError(f"{case['case_id']}: unknown derivation")
            case["rendering_a"] = transform(case["rendering_b"])
    validate_manifest(result)
    if result != manifest:
        raise ValueError("reconstructed renderings differ from the frozen manifest")
    return result


def verify_files(cases_dir):
    expected = json.loads(PROVENANCE.read_text())["case_files"]
    actual_names = {p.name for p in cases_dir.iterdir() if p.is_file()}
    if actual_names != set(expected):
        raise ValueError("frozen case file inventory differs from the baseline")
    for name, checksum in expected.items():
        if digest((cases_dir / name).read_bytes()) != checksum:
            raise ValueError(f"{name}: bytes differ from the pre-refactor baseline")


def replay(cases_dir, output_dir):
    cases_dir, output_dir = Path(cases_dir), Path(output_dir)
    if output_dir.resolve() == cases_dir.resolve():
        raise ValueError("replay output must be separate from frozen cases")
    verify_files(cases_dir)
    manifest = reconstruct(json.loads((cases_dir / "manifest.json").read_bytes()))
    generated = {
        "manifest.json": json.dumps(manifest, ensure_ascii=False, indent=2).encode(),
        # The archived preview predates the final F2 question wording.
        # Preserve it as evidence; it is not a rendering of the final manifest.
        "preview.md": (cases_dir / "preview.md").read_bytes(),
        "checker_report.json": json.dumps(
            contract_checker.build_report(manifest), ensure_ascii=False, indent=2
        ).encode(),
    }
    # Check the complete payloads before creating any output file.
    for name, data in generated.items():
        if data != (cases_dir / name).read_bytes():
            raise ValueError(f"{name}: replay differs from the frozen artifact")
    output_dir.mkdir(parents=True, exist_ok=True)
    for name, data in generated.items():
        (output_dir / name).write_bytes(data)
    return {name: digest(data) for name, data in generated.items()}
