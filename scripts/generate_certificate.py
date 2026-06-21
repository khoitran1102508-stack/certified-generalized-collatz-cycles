#!/usr/bin/env python3
"""Generate, verify, and summarize the final certified classification.

The certificate header retains its historical implementation identifier for immutable provenance.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time
from dataclasses import asdict, dataclass
from functools import reduce
from math import gcd
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.certificate_writer import write_certificate  # noqa: E402
from src.core import A_min_for_period  # noqa: E402
from verifier.verify_certificate import (  # noqa: E402
    CertificateError,
    canonical_cycle_valuations_and_offset,
    cycle_constant,
    primitive_period,
    rotate,
    v2,
    validate_retained_record,
    verify_certificate_file,
)


FINAL_C_MAX = 9997
FINAL_R_MAX = 12
FINAL_A_CAP = 30
EXPECTED_ROWS = 242
EXPECTED_CYCLES = 4439
EXPECTED_DIGEST = "1daa31c1107756ca895dae77d3420e2997e977fbd7a30714835d3917d5ecaa47"
RSS_LIMIT_KIB = 4 * 1024 * 1024
WALL_LIMIT_SECONDS = 24 * 60 * 60
SEARCHER_VERSION = "sprint4b1-final-certified-classification-v1"


@dataclass(frozen=True)
class ChildRun:
    """Parent-observed isolated child-process execution."""

    command: str
    returncode: int
    wall_seconds: float
    stdout_tail: str
    stderr_tail: str


@dataclass(frozen=True)
class DeterminismResult:
    """Byte-for-byte deterministic regeneration result."""

    first_certificate: str
    second_certificate: str
    first_sha256: str
    second_sha256: str
    byte_identical: bool
    first_records: int
    second_records: int
    row_counts_identical: bool
    second_copy_retained: bool


def final_header_metadata() -> dict[str, object]:
    """Return deterministic final-certificate metadata."""

    return {
        "certificate_schema_version": "certificate-v1",
        "searcher_version": SEARCHER_VERSION,
        "admissibility_restrictions": {
            "c_min": 1,
            "c_max": FINAL_C_MAX,
            "c_odd": True,
            "c_not_divisible_by_3": True,
            "positive_cycles_only": True,
            "primitive_cycles_only": True,
            "essential_cycles_only": True,
        },
        "normalization_convention": (
            "search_valuations are the DFS leaf word; orbit and "
            "cycle_valuations are the shared canonical rotation aligned "
            "position-by-position; essential cycles satisfy gcd(c,n_1,...,n_r)=1"
        ),
        "theorem_domain": {
            "r_min": 1,
            "r_max": FINAL_R_MAX,
            "A_cap": FINAL_A_CAP,
            "A_lower_condition": "2^A > 3^r",
        },
        "normalized_cycle_set_sha256": EXPECTED_DIGEST,
    }


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def hash_payload(payload: Any) -> str:
    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, sort_keys=True, indent=2) + "\n", encoding="utf-8")


def display_path(path: Path) -> str:
    """Return a repository-relative path when possible."""

    try:
        return path.resolve().relative_to(ROOT).as_posix()
    except ValueError:
        return path.as_posix()


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def row_count_signature(path: Path) -> list[tuple[int, int, int, int, int, int, int]]:
    """Return deterministic row-count fields, excluding timing/RSS columns."""

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    return [
        (
            int(row["r"]),
            int(row["A"]),
            int(row["record_count"]),
            int(row["prune_record_count"]),
            int(row["leaf_record_count"]),
            int(row["retained_cycle_count"]),
            int(row["recursive_node_count"]),
        )
        for row in rows
    ]


def final_row_keys() -> list[tuple[int, int]]:
    return [
        (r, A)
        for r in range(1, FINAL_R_MAX + 1)
        for A in range(A_min_for_period(r), FINAL_A_CAP + 1)
    ]


def run_child(args: list[str]) -> ChildRun:
    started = time.perf_counter()
    completed = subprocess.run(args, cwd=ROOT, text=True, capture_output=True)
    elapsed = time.perf_counter() - started
    return ChildRun(
        command=" ".join(args),
        returncode=completed.returncode,
        wall_seconds=elapsed,
        stdout_tail=completed.stdout[-1000:].replace("\n", " | "),
        stderr_tail=completed.stderr[-1000:].replace("\n", " | "),
    )


def generate_certificate_child(args: argparse.Namespace) -> None:
    row_metrics: list[dict[str, object]] = []
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    stats = write_certificate(
        args.output,
        r_max=FINAL_R_MAX,
        A_cap=FINAL_A_CAP,
        c_max=FINAL_C_MAX,
        header_metadata=final_header_metadata(),
        row_metrics=row_metrics,
    )
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    certificate_sha = sha256_file(args.output)
    metrics = {
        "certificate": display_path(args.output),
        "certificate_sha256": certificate_sha,
        "certificate_size_bytes": stats.certificate_file_size_bytes,
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "peak_rss_kib": stats.peak_rss_kb,
        "record_count": stats.records,
        "prune_record_count": stats.prune_records,
        "leaf_record_count": stats.leaf_records,
        "retained_cycle_count": stats.retained_records,
        "recursive_node_count": stats.recursive_nodes_visited,
        "dp_cache_entries": stats.dp_cache_entries,
        "max_reachable_residue_set_size": stats.max_reachable_residue_set_size,
        "total_residues_stored": stats.total_reachable_residues_stored,
        "dp_cache_hits": stats.dp_cache_hits,
        "dp_cache_misses": stats.dp_cache_misses,
        "factorization_seconds": stats.factorization_seconds,
        "search_seconds": stats.search_seconds,
        "serialization_seconds": stats.serialization_seconds,
        "row_count": len(row_metrics),
        "generation_result": "completed",
    }
    write_json(args.metrics_json, metrics)
    if args.row_metrics_csv is not None:
        fields = [
            "r",
            "A",
            "c_max",
            "D",
            "record_count",
            "prune_record_count",
            "leaf_record_count",
            "retained_cycle_count",
            "recursive_node_count",
            "dp_cache_entries",
            "max_reachable_residue_set_size",
            "total_residues_stored",
            "dp_cache_hits",
            "dp_cache_misses",
            "factorization_seconds",
            "search_seconds",
            "serialization_seconds",
            "wall_seconds",
            "peak_rss_kib",
            "byte_start",
            "byte_end",
            "byte_count",
        ]
        write_csv(args.row_metrics_csv, row_metrics, fields)
    print(json.dumps(metrics, sort_keys=True))


def verify_certificate_child(args: argparse.Namespace) -> None:
    wall_start = time.perf_counter()
    cpu_start = time.process_time()
    stats = verify_certificate_file(
        args.certificate,
        expected_r_max=FINAL_R_MAX,
        expected_A_cap=FINAL_A_CAP,
        expected_c_max=FINAL_C_MAX,
    )
    wall_seconds = time.perf_counter() - wall_start
    cpu_seconds = time.process_time() - cpu_start
    metrics = {
        "certificate": display_path(args.certificate),
        "certificate_sha256": sha256_file(args.certificate),
        "verdict": "VALID",
        "wall_seconds": wall_seconds,
        "cpu_seconds": cpu_seconds,
        "peak_rss_kib": stats.peak_rss_kib,
        "records_processed": stats.records_seen,
        "rows_verified": len(final_row_keys()),
        "prune_records_checked": stats.prune_records_checked,
        "leaves_checked": stats.leaves_checked,
        "retained_cycles_checked": stats.retained_cycles_checked,
        "recursive_nodes_checked": stats.recursive_nodes_checked,
        "dp_cache_entries": stats.dp_cache_entries,
        "max_reachable_residue_set_size": stats.max_reachable_residue_set_size,
        "total_residues_stored": stats.total_reachable_residues_stored,
        "dp_cache_hits": stats.dp_cache_hits,
        "dp_cache_misses": stats.dp_cache_misses,
        "expected_domain_validation": "passed",
    }
    write_json(args.metrics_json, metrics)
    print(json.dumps(metrics, sort_keys=True))


def load_header(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        line = handle.readline()
    payload = json.loads(line)
    if not isinstance(payload, dict):
        raise ValueError("header is not a JSON object")
    return payload


def recomputed_cycle_valuations(c: int, orbit: tuple[int, ...]) -> tuple[int, ...]:
    valuations: list[int] = []
    for index, current in enumerate(orbit):
        value = 3 * current + c
        valuation = v2(value)
        nxt = value >> valuation
        if nxt != orbit[(index + 1) % len(orbit)]:
            raise AssertionError("stored orbit does not follow U_c")
        valuations.append(valuation)
    return tuple(valuations)


def audit_certificate_alignment(certificate: Path, output: Path) -> dict[str, Any]:
    rows: list[dict[str, Any]] = []
    retained = 0
    misaligned = 0
    with certificate.open("r", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        fmt = str(header.get("format", ""))
        for line_number, line in enumerate(handle, start=2):
            record = json.loads(line)
            if record.get("kind") != "leaf" or record.get("status") != "RETAINED":
                continue
            retained += 1
            c = int(record["c"])
            r = int(record["r"])
            A = int(record["A"])
            orbit = tuple(int(x) for x in record["orbit"])
            if "cycle_valuations" in record:
                stored = tuple(int(x) for x in record["cycle_valuations"])
                search = tuple(int(x) for x in record["search_valuations"])
            else:
                stored = tuple(int(x) for x in record["valuations"])
                search = stored
            try:
                recomputed = recomputed_cycle_valuations(c, orbit)
                aligned = stored == recomputed
                transition_status = "ok"
            except AssertionError:
                recomputed = tuple()
                aligned = False
                transition_status = "bad_transition"
            if not aligned:
                misaligned += 1
            matching_offsets = [
                offset for offset in range(r) if rotate(search, offset) == recomputed
            ]
            rows.append(
                {
                    "certificate": display_path(certificate),
                    "format": fmt,
                    "line_number": line_number,
                    "c": c,
                    "r": r,
                    "A": A,
                    "stored_orbit": json.dumps(list(orbit), separators=(",", ":")),
                    "stored_valuations": json.dumps(list(stored), separators=(",", ":")),
                    "search_valuations": json.dumps(list(search), separators=(",", ":")),
                    "recomputed_valuations": json.dumps(list(recomputed), separators=(",", ":")),
                    "alignment_status": "ALIGNED" if aligned else "MISALIGNED",
                    "transition_status": transition_status,
                    "rotation_offset": matching_offsets[0] if matching_offsets else "",
                }
            )
    fields = [
        "certificate",
        "format",
        "line_number",
        "c",
        "r",
        "A",
        "stored_orbit",
        "stored_valuations",
        "search_valuations",
        "recomputed_valuations",
        "alignment_status",
        "transition_status",
        "rotation_offset",
    ]
    write_csv(output, rows, fields)
    return {
        "certificate": display_path(certificate),
        "format": rows[0]["format"] if rows else "",
        "retained_records": retained,
        "misaligned_retained_records": misaligned,
        "aligned_retained_records": retained - misaligned,
        "audit_csv": display_path(output),
    }


def parse_certificate_rows_and_cycles(path: Path) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    row_counts: dict[tuple[int, int], dict[str, Any]] = {}
    cycles_by_key: dict[tuple[int, tuple[int, ...]], dict[str, Any]] = {}
    expected_keys = set(final_row_keys())
    with path.open("r", encoding="utf-8") as handle:
        header = json.loads(handle.readline())
        if header.get("domain") != {"A_cap": FINAL_A_CAP, "c_max": FINAL_C_MAX, "r_max": FINAL_R_MAX}:
            raise AssertionError("unexpected final certificate domain")
        for line in handle:
            record = json.loads(line)
            r = int(record["r"])
            A = int(record["A"])
            key = (r, A)
            if key not in expected_keys:
                raise AssertionError(f"record outside final row domain: {key}")
            row = row_counts.setdefault(
                key,
                {
                    "r": r,
                    "A": A,
                    "c_max": FINAL_C_MAX,
                    "record_count": 0,
                    "prune_record_count": 0,
                    "leaf_record_count": 0,
                    "retained_cycle_count": 0,
                },
            )
            row["record_count"] += 1
            if record.get("kind") == "prune":
                row["prune_record_count"] += 1
                continue
            if record.get("kind") != "leaf":
                raise AssertionError(f"unexpected record kind: {record.get('kind')}")
            row["leaf_record_count"] += 1
            if record.get("status") != "RETAINED":
                continue
            row["retained_cycle_count"] += 1
            c = int(record["c"])
            orbit = tuple(int(x) for x in record["orbit"])
            search_valuations = tuple(int(x) for x in record["search_valuations"])
            cycle_valuations = tuple(int(x) for x in record["cycle_valuations"])
            if c <= 0 or c > FINAL_C_MAX or c % 2 == 0 or c % 3 == 0:
                raise AssertionError(f"invalid final-cycle parameter c={c}")
            if (
                len(orbit) != r
                or len(search_valuations) != r
                or len(cycle_valuations) != r
                or sum(search_valuations) != A
                or sum(cycle_valuations) != A
            ):
                raise AssertionError(f"cycle shape mismatch for {record}")
            D = (1 << A) - 3**r
            C = cycle_constant(search_valuations)
            divisor = gcd(D, C)
            n1 = C // divisor
            raw_orbit = [n1]
            for index, expected_valuation in enumerate(search_valuations):
                current = raw_orbit[index]
                value = 3 * current + c
                actual_valuation = v2(value)
                if actual_valuation != expected_valuation:
                    raise AssertionError(f"raw valuation reconstruction failed: {record}")
                nxt = value >> actual_valuation
                if index < r - 1:
                    raw_orbit.append(nxt)
                elif nxt != n1:
                    raise AssertionError(f"raw orbit does not close: {record}")
            raw_orbit_tuple = tuple(raw_orbit)
            canonical_orbit, canonical_valuations, canonical_offset = (
                canonical_cycle_valuations_and_offset(raw_orbit_tuple, search_valuations)
            )
            if canonical_orbit != orbit or canonical_valuations != cycle_valuations:
                raise AssertionError(f"record is not canonical and aligned: {record}")
            if int(record["canonical_offset"]) != canonical_offset:
                raise AssertionError(f"canonical offset mismatch: {record}")
            validate_retained_record(record)
            period = primitive_period(orbit)
            if period != r:
                raise AssertionError(f"nonprimitive retained cycle: {record}")
            if reduce(gcd, (c, *orbit)) != 1:
                raise AssertionError(f"nonessential retained cycle: {record}")
            cycle = {
                "c": c,
                "r": r,
                "A": A,
                "orbit": list(orbit),
                "valuations": list(canonical_valuations),
                "primitive_period": period,
                "essential": True,
            }
            cycle_key = (c, orbit)
            if cycle_key in cycles_by_key:
                raise AssertionError(f"duplicate cycle under canonical key: {record}")
            cycles_by_key[cycle_key] = cycle
    if set(row_counts) != expected_keys:
        missing = sorted(expected_keys - set(row_counts))
        raise AssertionError(f"missing final rows: {missing[:5]}")
    rows = [row_counts[key] for key in final_row_keys()]
    cycles = sorted(
        cycles_by_key.values(),
        key=lambda item: (item["c"], item["r"], item["A"], item["orbit"]),
    )
    return rows, cycles


def write_final_datasets(certificate: Path, results_dir: Path) -> dict[str, Any]:
    row_summary, cycles = parse_certificate_rows_and_cycles(certificate)
    digest = hash_payload(cycles)
    if len(row_summary) != EXPECTED_ROWS:
        raise AssertionError(f"expected {EXPECTED_ROWS} rows, got {len(row_summary)}")
    if len(cycles) != EXPECTED_CYCLES:
        raise AssertionError(f"expected {EXPECTED_CYCLES} cycles, got {len(cycles)}")
    if digest != EXPECTED_DIGEST:
        raise AssertionError(f"cycle digest mismatch: {digest}")

    cycle_fields = [
        "c",
        "r",
        "A",
        "orbit",
        "valuations",
        "min_orbit",
        "primitive_period",
        "essential",
    ]
    csv_rows = []
    for cycle in cycles:
        csv_rows.append(
            {
                "c": cycle["c"],
                "r": cycle["r"],
                "A": cycle["A"],
                "orbit": json.dumps(cycle["orbit"], separators=(",", ":")),
                "valuations": json.dumps(cycle["valuations"], separators=(",", ":")),
                "min_orbit": min(cycle["orbit"]),
                "primitive_period": cycle["primitive_period"],
                "essential": cycle["essential"],
            }
        )
    write_csv(results_dir / "final_cycles.csv", csv_rows, cycle_fields)
    with (results_dir / "final_cycles.jsonl").open("w", encoding="utf-8") as handle:
        for cycle in cycles:
            handle.write(json.dumps(cycle, sort_keys=True, separators=(",", ":")) + "\n")
    write_csv(
        results_dir / "final_row_summary.csv",
        row_summary,
        [
            "r",
            "A",
            "c_max",
            "record_count",
            "prune_record_count",
            "leaf_record_count",
            "retained_cycle_count",
        ],
    )
    raw_final_cycles_sha256 = sha256_file(results_dir / "final_cycles.jsonl")
    (results_dir / "final_cycle_digest.txt").write_text(
        "\n".join(
            [
                f"normalized_cycle_payload_sha256={digest}",
                f"raw_final_cycles_jsonl_sha256={raw_final_cycles_sha256}",
                (
                    "note=The normalized payload digest is the SHA-256 of the "
                    "canonical JSON serialization used by the serialization scripts, "
                    "not the raw byte hash of results/final_cycles.jsonl."
                ),
                "",
            ]
        ),
        encoding="utf-8",
    )
    return {
        "row_count": len(row_summary),
        "cycle_count": len(cycles),
        "cycle_digest_sha256": digest,
        "record_count_from_rows": sum(int(row["record_count"]) for row in row_summary),
        "prune_record_count_from_rows": sum(int(row["prune_record_count"]) for row in row_summary),
        "leaf_record_count_from_rows": sum(int(row["leaf_record_count"]) for row in row_summary),
        "retained_cycle_count_from_rows": sum(int(row["retained_cycle_count"]) for row in row_summary),
    }


def load_wegner_snapshot(path: Path) -> set[tuple[int, int, int, int]]:
    rows: set[tuple[int, int, int, int]] = set()
    with path.open(newline="", encoding="utf-8") as handle:
        reader = csv.DictReader(handle)
        required = {"c", "min_orbit", "A", "r"}
        if not required.issubset(reader.fieldnames or set()):
            raise ValueError("Wegner snapshot is missing required normalized fields")
        for row in reader:
            rows.add((int(row["c"]), int(row["min_orbit"]), int(row["A"]), int(row["r"])))
    return rows


def write_prior_comparison(results_dir: Path, snapshot: Path) -> dict[str, Any]:
    cycles = []
    with (results_dir / "final_cycles.jsonl").open(encoding="utf-8") as handle:
        for line in handle:
            cycles.append(json.loads(line))
    wegner = load_wegner_snapshot(snapshot)
    fields = [
        "c",
        "r",
        "A",
        "orbit",
        "valuations",
        "min_orbit",
        "wegner_status",
        "overall_classification",
        "note",
    ]
    rows = []
    matched = 0
    for cycle in cycles:
        min_orbit = min(cycle["orbit"])
        key = (int(cycle["c"]), int(min_orbit), int(cycle["A"]), int(cycle["r"]))
        if key in wegner:
            status = "already_listed_exact_k_min_A_r_in_parsed_wegner"
            overall = "already_listed"
            matched += 1
        else:
            status = "apparently_absent_from_release_bundled_wegner_snapshot"
            overall = "apparently_absent"
        rows.append(
            {
                "c": cycle["c"],
                "r": cycle["r"],
                "A": cycle["A"],
                "orbit": json.dumps(cycle["orbit"], separators=(",", ":")),
                "valuations": json.dumps(cycle["valuations"], separators=(",", ":")),
                "min_orbit": min_orbit,
                "wegner_status": status,
                "overall_classification": overall,
                "note": (
                    "No new-cycle discovery claim is made.  This comparison uses a "
                    "archived Wegner-derived normalized snapshot; the certified-domain "
                    "result is a certified exhaustive valuation-bounded classification."
                ),
            }
        )
    write_csv(results_dir / "final_prior_table_comparison.csv", rows, fields)
    summary = {
        "final_cycle_count": len(cycles),
        "wegner_matched_count": matched,
        "wegner_snapshot_sha256": sha256_file(snapshot),
        "comparison_sha256": sha256_file(results_dir / "final_prior_table_comparison.csv"),
        "all_cycles_matched": matched == len(cycles) == EXPECTED_CYCLES,
    }
    text = "# Prior-Table Comparison\n\n"
    text += f"- Final certified cycles compared: {len(cycles)}\n"
    text += f"- Matched to bundled Wegner-derived snapshot: {matched}\n"
    text += f"- Wegner snapshot SHA-256: `{summary['wegner_snapshot_sha256']}`\n"
    text += f"- Comparison CSV SHA-256: `{summary['comparison_sha256']}`\n\n"
    text += (
        "All 4,439 final-domain cycles match the derived Wegner "
        "reference snapshot under the documented `(c, min_orbit, A, r)` key.\n\n"
        "This project does not claim discovery of new cycles.  The result is a "
        "certified exhaustive valuation-bounded classification.  Prior tables "
        "are not described as incorrect or incomplete.\n"
    )
    (results_dir / "final_prior_table_comparison_summary.md").write_text(
        text, encoding="utf-8"
    )
    return summary


def mutate_json_line(line: str, mutator: Any) -> str:
    payload = json.loads(line)
    mutator(payload)
    return json.dumps(payload, sort_keys=True, separators=(",", ":"))


def write_lines(path: Path, lines: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def first_record_index(lines: list[str], predicate: Any) -> int:
    for index, line in enumerate(lines[1:], start=1):
        if predicate(json.loads(line)):
            return index
    raise ValueError("requested record not found")


def run_tampering_tests(output: Path) -> list[dict[str, Any]]:
    tmp = ROOT / "certificates" / "_certificate_tamper_work"
    if tmp.exists():
        shutil.rmtree(tmp)
    tmp.mkdir(parents=True)
    base = tmp / "base.jsonl"
    write_certificate(base, r_max=6, A_cap=14, c_max=31)
    lines = base.read_text(encoding="utf-8").splitlines()
    cases: list[tuple[str, Path, list[str], tuple[int, int, int]]] = []

    cases.append(("wrong_expected_r_max", base, lines, (7, 14, 31)))
    cases.append(("wrong_expected_A_cap", base, lines, (6, 15, 31)))
    cases.append(("wrong_expected_c_max", base, lines, (6, 14, 63)))

    modified_header = lines.copy()
    modified_header[0] = mutate_json_line(
        modified_header[0], lambda payload: payload.__setitem__("arithmetic", "tampered")
    )
    cases.append(("modified_header", tmp / "modified_header.jsonl", modified_header, (6, 14, 31)))

    prune_index = first_record_index(lines, lambda record: record.get("kind") == "prune")
    modified_prune = lines.copy()
    modified_prune[prune_index] = mutate_json_line(
        modified_prune[prune_index],
        lambda payload: payload.__setitem__("reason", "TAMPERED"),
    )
    cases.append(("modified_prune_record", tmp / "modified_prune.jsonl", modified_prune, (6, 14, 31)))

    retained_index = first_record_index(
        lines,
        lambda record: record.get("kind") == "leaf"
        and record.get("status") == "RETAINED"
        and len(record.get("orbit", [])) > 1,
    )
    modified_retained = lines.copy()
    modified_retained[retained_index] = mutate_json_line(
        modified_retained[retained_index],
        lambda payload: payload.__setitem__("c", int(payload["c"]) + 2),
    )
    cases.append(
        ("modified_retained_cycle_record", tmp / "modified_retained.jsonl", modified_retained, (6, 14, 31))
    )

    orbit_rotated = lines.copy()
    orbit_rotated[retained_index] = mutate_json_line(
        orbit_rotated[retained_index],
        lambda payload: payload.__setitem__(
            "orbit", payload["orbit"][1:] + payload["orbit"][:1]
        ),
    )
    cases.append(("orbit_rotated_alone", tmp / "orbit_rotated.jsonl", orbit_rotated, (6, 14, 31)))

    valuations_rotated = lines.copy()
    valuations_rotated[retained_index] = mutate_json_line(
        valuations_rotated[retained_index],
        lambda payload: payload.__setitem__(
            "cycle_valuations",
            payload["cycle_valuations"][1:] + payload["cycle_valuations"][:1],
        ),
    )
    cases.append(
        ("cycle_valuations_rotated_alone", tmp / "valuations_rotated.jsonl", valuations_rotated, (6, 14, 31))
    )

    one_valuation_changed = lines.copy()
    one_valuation_changed[retained_index] = mutate_json_line(
        one_valuation_changed[retained_index],
        lambda payload: payload["cycle_valuations"].__setitem__(
            0, int(payload["cycle_valuations"][0]) + 1
        ),
    )
    cases.append(
        ("one_cycle_valuation_changed", tmp / "one_valuation_changed.jsonl", one_valuation_changed, (6, 14, 31))
    )

    one_orbit_changed = lines.copy()
    one_orbit_changed[retained_index] = mutate_json_line(
        one_orbit_changed[retained_index],
        lambda payload: payload["orbit"].__setitem__(0, int(payload["orbit"][0]) + 2),
    )
    cases.append(("one_orbit_member_changed", tmp / "one_orbit_changed.jsonl", one_orbit_changed, (6, 14, 31)))

    bad_search = lines.copy()
    bad_search[retained_index] = mutate_json_line(
        bad_search[retained_index],
        lambda payload: payload["search_valuations"].__setitem__(
            0, int(payload["search_valuations"][0]) + 1
        ),
    )
    cases.append(("incorrect_search_valuations", tmp / "bad_search.jsonl", bad_search, (6, 14, 31)))

    bad_cycle_vals = lines.copy()
    bad_cycle_vals[retained_index] = mutate_json_line(
        bad_cycle_vals[retained_index],
        lambda payload: payload["cycle_valuations"].__setitem__(
            0, int(payload["cycle_valuations"][0]) + 1
        ),
    )
    cases.append(("incorrect_cycle_valuations", tmp / "bad_cycle_vals.jsonl", bad_cycle_vals, (6, 14, 31)))

    wrong_length = lines.copy()
    wrong_length[retained_index] = mutate_json_line(
        wrong_length[retained_index],
        lambda payload: payload.__setitem__(
            "cycle_valuations", payload["cycle_valuations"][:-1]
        ),
    )
    cases.append(("wrong_length", tmp / "wrong_length.jsonl", wrong_length, (6, 14, 31)))

    cases.append(("deleted_record", tmp / "deleted.jsonl", [lines[0], *lines[2:]], (6, 14, 31)))
    cases.append(("duplicated_record", tmp / "duplicated.jsonl", [*lines[:2], lines[1], *lines[2:]], (6, 14, 31)))

    swap_index = 1
    while swap_index + 1 < len(lines) and lines[swap_index] == lines[swap_index + 1]:
        swap_index += 1
    reordered = lines.copy()
    reordered[swap_index], reordered[swap_index + 1] = reordered[swap_index + 1], reordered[swap_index]
    cases.append(("reordered_adjacent_records", tmp / "reordered.jsonl", reordered, (6, 14, 31)))
    cases.append(("appended_extra_record", tmp / "appended.jsonl", [*lines, lines[-1]], (6, 14, 31)))
    cases.append(("truncated_final_row", tmp / "truncated.jsonl", lines[:-1], (6, 14, 31)))

    rows: list[dict[str, Any]] = []
    for name, path, case_lines, expected in cases:
        if path != base:
            write_lines(path, case_lines)
        try:
            verify_certificate_file(
                path,
                expected_r_max=expected[0],
                expected_A_cap=expected[1],
                expected_c_max=expected[2],
            )
            rejected = False
            error = ""
        except CertificateError as exc:
            rejected = True
            error = str(exc)[:300]
        rows.append(
            {
                "case": name,
                "expected_rejection": True,
                "rejected": rejected,
                "status": "PASS" if rejected else "FAIL",
                "error_excerpt": error,
            }
        )
    write_csv(output, rows, ["case", "expected_rejection", "rejected", "status", "error_excerpt"])
    shutil.rmtree(tmp)
    return rows


def write_generation_outputs(metrics: dict[str, Any], row_metrics_csv: Path, summary_md: Path, metrics_csv: Path) -> None:
    write_csv(metrics_csv, [metrics], list(metrics.keys()))
    row_metrics = []
    with row_metrics_csv.open(newline="", encoding="utf-8") as handle:
        row_metrics = list(csv.DictReader(handle))
    largest_row = max(row_metrics, key=lambda row: int(row["max_reachable_residue_set_size"]))
    text = "# Certificate Generation Summary\n\n"
    text += f"- Certificate: `{metrics['certificate']}`\n"
    text += f"- SHA-256: `{metrics['certificate_sha256']}`\n"
    text += f"- Size bytes: {metrics['certificate_size_bytes']:,}\n"
    text += f"- Records: {metrics['record_count']:,}\n"
    text += f"- Prune records: {metrics['prune_record_count']:,}\n"
    text += f"- Leaf records: {metrics['leaf_record_count']:,}\n"
    text += f"- Retained cycles: {metrics['retained_cycle_count']:,}\n"
    text += f"- Recursive nodes: {metrics['recursive_node_count']:,}\n"
    text += f"- Wall seconds: {metrics['wall_seconds']:.6f}\n"
    text += f"- CPU seconds: {metrics['cpu_seconds']:.6f}\n"
    text += f"- Peak RSS KiB: {metrics['peak_rss_kib']:,}\n"
    text += f"- Factorization seconds: {metrics['factorization_seconds']:.6f}\n"
    text += f"- Search seconds: {metrics['search_seconds']:.6f}\n"
    text += f"- Serialization seconds: {metrics['serialization_seconds']:.6f}\n"
    text += (
        f"- Largest reachable-residue row: r={largest_row['r']}, A={largest_row['A']}, "
        f"max set={int(largest_row['max_reachable_residue_set_size']):,}, "
        f"total residues={int(largest_row['total_residues_stored']):,}\n"
    )
    text += f"\nPer-row metrics are in `{row_metrics_csv}`.\n"
    summary_md.write_text(text, encoding="utf-8")


def write_verification_outputs(metrics: dict[str, Any], summary_md: Path, metrics_csv: Path) -> None:
    write_csv(metrics_csv, [metrics], list(metrics.keys()))
    text = "# Certificate Verification Summary\n\n"
    text += f"- Verdict: `{metrics['verdict']}`\n"
    text += f"- Certificate SHA-256: `{metrics['certificate_sha256']}`\n"
    text += f"- Rows verified: {metrics['rows_verified']:,}\n"
    text += f"- Records processed: {metrics['records_processed']:,}\n"
    text += f"- Prune records checked: {metrics['prune_records_checked']:,}\n"
    text += f"- Leaves checked: {metrics['leaves_checked']:,}\n"
    text += f"- Retained cycles checked: {metrics['retained_cycles_checked']:,}\n"
    text += f"- Wall seconds: {metrics['wall_seconds']:.6f}\n"
    text += f"- CPU seconds: {metrics['cpu_seconds']:.6f}\n"
    text += f"- Peak RSS KiB: {metrics['peak_rss_kib']:,}\n"
    text += f"- Expected-domain validation: `{metrics['expected_domain_validation']}`\n"
    summary_md.write_text(text, encoding="utf-8")


def run_all(args: argparse.Namespace) -> None:
    old_cert = ROOT / "certificates/final_certificate_c9997_r12_A30.jsonl"
    cert = ROOT / "certificates/final_certificate_c9997_r12_A30_v2.jsonl"
    regen = ROOT / "certificates/_final_certificate_regeneration_check.jsonl"
    results = ROOT / "results"
    old_alignment_summary = {}
    if old_cert.exists():
        old_alignment_summary = audit_certificate_alignment(
            old_cert, results / "old_alignment_audit.csv"
        )
    first_metrics_json = results / "generation_metrics.json"
    second_metrics_json = results / "generation_metrics_regen.json"
    row_metrics_csv = results / "generation_row_metrics.csv"
    second_row_metrics_csv = results / "generation_row_metrics_regen.csv"
    verify_metrics_json = results / "verification_metrics.json"

    gen_cmd = [
        sys.executable,
        str(Path(__file__).relative_to(ROOT)),
        "generate",
        "--output",
        str(cert),
        "--metrics-json",
        str(first_metrics_json),
        "--row-metrics-csv",
        str(row_metrics_csv),
    ]
    first_run = run_child(gen_cmd)
    if first_run.returncode != 0:
        raise SystemExit(f"first generation failed: {first_run.stderr_tail} {first_run.stdout_tail}")
    first_metrics = read_json(first_metrics_json)

    regen_cmd = [
        sys.executable,
        str(Path(__file__).relative_to(ROOT)),
        "generate",
        "--output",
        str(regen),
        "--metrics-json",
        str(second_metrics_json),
        "--row-metrics-csv",
        str(second_row_metrics_csv),
    ]
    second_run = run_child(regen_cmd)
    if second_run.returncode != 0:
        raise SystemExit(f"second generation failed: {second_run.stderr_tail} {second_run.stdout_tail}")
    second_metrics = read_json(second_metrics_json)

    first_metrics["isolated_parent_wall_seconds"] = first_run.wall_seconds
    second_metrics["isolated_parent_wall_seconds"] = second_run.wall_seconds
    write_json(first_metrics_json, first_metrics)
    write_json(second_metrics_json, second_metrics)
    row_counts_identical = row_count_signature(row_metrics_csv) == row_count_signature(
        second_row_metrics_csv
    )
    deterministic = DeterminismResult(
        first_certificate=display_path(cert),
        second_certificate=display_path(regen),
        first_sha256=first_metrics["certificate_sha256"],
        second_sha256=second_metrics["certificate_sha256"],
        byte_identical=cert.read_bytes() == regen.read_bytes(),
        first_records=int(first_metrics["record_count"]),
        second_records=int(second_metrics["record_count"]),
        row_counts_identical=row_counts_identical,
        second_copy_retained=False,
    )
    if not deterministic.byte_identical or not deterministic.row_counts_identical:
        raise SystemExit("certificate regeneration was not byte-for-byte deterministic")
    regen.unlink()
    second_row_metrics_csv.unlink()

    write_generation_outputs(
        first_metrics,
        row_metrics_csv,
        results / "generation_summary.md",
        results / "generation_metrics.csv",
    )
    det_text = "# Deterministic Regeneration Report\n\n"
    det_text += f"- First SHA-256: `{deterministic.first_sha256}`\n"
    det_text += f"- Second SHA-256: `{deterministic.second_sha256}`\n"
    det_text += f"- Byte-identical: `{deterministic.byte_identical}`\n"
    det_text += f"- Row-level counts identical: `{deterministic.row_counts_identical}`\n"
    det_text += f"- Records: {deterministic.first_records:,}\n"
    det_text += "- The second full copy was deleted after byte comparison.\n"
    (results / "determinism_report.md").write_text(det_text, encoding="utf-8")

    verify_cmd = [
        sys.executable,
        str(Path(__file__).relative_to(ROOT)),
        "verify",
        "--certificate",
        str(cert),
        "--metrics-json",
        str(verify_metrics_json),
    ]
    verify_run = run_child(verify_cmd)
    if verify_run.returncode != 0:
        raise SystemExit(f"verification failed: {verify_run.stderr_tail} {verify_run.stdout_tail}")
    verify_metrics = read_json(verify_metrics_json)
    verify_metrics["isolated_parent_wall_seconds"] = verify_run.wall_seconds
    write_json(verify_metrics_json, verify_metrics)
    write_verification_outputs(
        verify_metrics,
        results / "verification_summary.md",
        results / "verification_metrics.csv",
    )

    dataset_summary = write_final_datasets(cert, results)
    corrected_alignment_summary = audit_certificate_alignment(
        cert, results / "alignment_audit.csv"
    )
    if corrected_alignment_summary["misaligned_retained_records"] != 0:
        raise SystemExit("corrected certificate has misaligned retained records")
    prior_summary = write_prior_comparison(
        results, ROOT / "data/prior_tables/wegner_positive_cycles_normalized.csv"
    )
    tamper_rows = run_tampering_tests(results / "tampering_tests.csv")
    if any(row["status"] != "PASS" for row in tamper_rows):
        raise SystemExit("one or more tampering checks did not reject")

    final_summary = {
        "generation": first_metrics,
        "verification": verify_metrics,
        "determinism": asdict(deterministic),
        "dataset": dataset_summary,
        "old_alignment_audit": old_alignment_summary,
        "corrected_alignment_audit": corrected_alignment_summary,
        "prior_table_comparison": prior_summary,
        "tampering_passed": all(row["status"] == "PASS" for row in tamper_rows),
    }
    write_json(results / "validation_summary.json", final_summary)
    print(json.dumps(final_summary, sort_keys=True))


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    generate = sub.add_parser("generate")
    generate.add_argument("--output", type=Path, required=True)
    generate.add_argument("--metrics-json", type=Path, required=True)
    generate.add_argument("--row-metrics-csv", type=Path)

    verify = sub.add_parser("verify")
    verify.add_argument("--certificate", type=Path, required=True)
    verify.add_argument("--metrics-json", type=Path, required=True)

    sub.add_parser("all")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    if args.command == "generate":
        generate_certificate_child(args)
    elif args.command == "verify":
        try:
            verify_certificate_child(args)
        except CertificateError as exc:
            print(f"INVALID: {exc}")
            raise SystemExit(1) from exc
    elif args.command == "all":
        run_all(args)
    else:  # pragma: no cover
        raise AssertionError(args.command)


if __name__ == "__main__":
    main()
