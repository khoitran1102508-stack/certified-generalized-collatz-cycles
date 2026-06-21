"""Deterministic certificate-v1 writer for the divisor-threshold sieve."""
from __future__ import annotations

import argparse
import json
import sys
import time
from dataclasses import dataclass
from math import gcd
from pathlib import Path
from typing import TextIO

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on some platforms
    resource = None  # type: ignore[assignment]

try:
    from .core import A_min_for_period, canonical_rotation, cycle_constant, primitive_period
    from .divisor_sieve import (
        normalized_cycle_from_valuations,
        prefix_can_reach_threshold,
        prefix_constant_after_append,
    )
    from .divisors import eligible_divisors
    from .reachable_residues import ReachableResidueOracle
except ImportError:  # direct script execution
    from core import A_min_for_period, canonical_rotation, cycle_constant, primitive_period  # type: ignore
    from divisor_sieve import (  # type: ignore
        normalized_cycle_from_valuations,
        prefix_can_reach_threshold,
        prefix_constant_after_append,
    )
    from divisors import eligible_divisors  # type: ignore
    from reachable_residues import ReachableResidueOracle  # type: ignore


FORMAT = "collatz-divisor-sieve-v1"
ROW_FORMAT = "collatz-divisor-sieve-row-v1"
ORDERING = "r,A,depth-first-parts-ascending"
ROW_ORDERING = "single-row,depth-first-parts-ascending"
ARITHMETIC = "exact-integers"


@dataclass(frozen=True)
class CertificateStats:
    """Counters and instrumentation for a generated certificate."""

    records: int
    prune_records: int
    leaf_records: int
    retained_records: int
    recursive_nodes_visited: int
    dp_cache_entries: int
    max_reachable_residue_set_size: int
    total_reachable_residues_stored: int
    dp_cache_hits: int
    dp_cache_misses: int
    factorization_seconds: float
    search_seconds: float
    serialization_seconds: float
    certificate_file_size_bytes: int
    peak_rss_kb: int


def _peak_rss_kb() -> int:
    """Return current process peak RSS in kilobytes when available."""
    if resource is None:
        return 0
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return value // 1024
    return value


def _write_json_line(handle: TextIO, payload: dict[str, object]) -> float:
    started = time.perf_counter()
    handle.write(json.dumps(payload, sort_keys=True, separators=(",", ":")))
    handle.write("\n")
    return time.perf_counter() - started


def _leaf_record(
    r: int, A: int, search_valuations: tuple[int, ...], D: int, c_max: int
) -> dict[str, object]:
    C = cycle_constant(search_valuations)
    c = D // gcd(D, C)
    record: dict[str, object] = {
        "kind": "leaf",
        "r": r,
        "A": A,
        "search_valuations": list(search_valuations),
    }
    if c > c_max:
        record["status"] = "PARAMETER_ABOVE_CAP"
        return record
    if search_valuations != canonical_rotation(search_valuations):
        record["status"] = "NONCANONICAL_ROTATION"
        return record
    if primitive_period(search_valuations) != r:
        record["status"] = "IMPRIMITIVE_VALUATION_VECTOR"
        return record

    cycle = normalized_cycle_from_valuations(search_valuations, D)
    if cycle is None:
        raise AssertionError(
            f"retained valuation vector failed verification: {search_valuations}"
        )
    if cycle.c != c or cycle.c > c_max:
        raise AssertionError("retained cycle parameter mismatch")
    record["status"] = "RETAINED"
    record["c"] = cycle.c
    record["orbit"] = list(cycle.orbit)
    record["cycle_valuations"] = list(cycle.valuations)
    record["canonical_offset"] = cycle.canonical_offset
    return record


def write_certificate(
    path: Path,
    *,
    r_max: int,
    A_cap: int,
    c_max: int,
    header_metadata: dict[str, object] | None = None,
    row_metrics: list[dict[str, object]] | None = None,
) -> CertificateStats:
    """Write a deterministic certificate-v1 JSONL file."""
    if r_max <= 0 or A_cap <= 0 or c_max <= 0:
        raise ValueError("r_max, A_cap, and c_max must be positive")

    path.parent.mkdir(parents=True, exist_ok=True)
    counters = {
        "records": 0,
        "prune": 0,
        "leaf": 0,
        "retained": 0,
        "recursive_nodes": 0,
        "dp_cache_entries": 0,
        "max_set_size": 0,
        "total_residues": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }
    factorization_seconds = 0.0
    serialization_seconds = 0.0
    header = {
        "format": FORMAT,
        "domain": {"r_max": r_max, "A_cap": A_cap, "c_max": c_max},
        "ordering": ORDERING,
        "arithmetic": ARITHMETIC,
    }
    if header_metadata is not None:
        protected = {"format", "domain", "ordering", "arithmetic"}
        overlap = protected.intersection(header_metadata)
        if overlap:
            raise ValueError(f"header metadata may not override {sorted(overlap)}")
        header.update(header_metadata)

    total_start = time.perf_counter()
    with path.open("w", encoding="utf-8") as handle:
        serialization_seconds += _write_json_line(handle, header)

        for r in range(1, r_max + 1):
            amin = A_min_for_period(r)
            for A in range(amin, A_cap + 1):
                row_start = time.perf_counter()
                row_byte_start = handle.tell()
                row_records_start = counters["records"]
                row_prune_start = counters["prune"]
                row_leaf_start = counters["leaf"]
                row_retained_start = counters["retained"]
                row_nodes_start = counters["recursive_nodes"]
                row_serialization_start = serialization_seconds
                D = (1 << A) - 3**r
                if D <= 0:
                    raise AssertionError("A_min admitted nonpositive denominator")
                factor_start = time.perf_counter()
                eligible = eligible_divisors(D, c_max)
                row_factorization_seconds = time.perf_counter() - factor_start
                factorization_seconds += row_factorization_seconds
                oracle = ReachableResidueOracle()
                prefix: list[int] = []

                def emit(record: dict[str, object]) -> None:
                    nonlocal serialization_seconds
                    serialization_seconds += _write_json_line(handle, record)
                    counters["records"] += 1
                    if record["kind"] == "prune":
                        counters["prune"] += 1
                    elif record["kind"] == "leaf":
                        counters["leaf"] += 1
                        if record.get("status") == "RETAINED":
                            counters["retained"] += 1

                def dfs(t: int, S: int, P: int) -> None:
                    counters["recursive_nodes"] += 1
                    if t == r:
                        emit(_leaf_record(r, A, tuple(prefix), D, c_max))
                        return
                    if not prefix_can_reach_threshold(
                        r=r,
                        A=A,
                        D=D,
                        c_max=c_max,
                        t=t,
                        S=S,
                        P=P,
                        eligible=eligible,
                        oracle=oracle,
                    ):
                        emit(
                            {
                                "kind": "prune",
                                "r": r,
                                "A": A,
                                "prefix": list(prefix),
                                "reason": "NO_ELIGIBLE_DIVISOR_REACHABLE",
                            }
                        )
                        return

                    remaining_parts_after_next = r - (t + 1)
                    if remaining_parts_after_next == 0:
                        choices = range(A - S, A - S + 1)
                    else:
                        max_next = A - S - remaining_parts_after_next
                        choices = range(1, max_next + 1)
                    for next_part in choices:
                        prefix.append(next_part)
                        next_P = prefix_constant_after_append(r, t, S, P)
                        dfs(t + 1, S + next_part, next_P)
                        prefix.pop()

                dfs(0, 0, 0)
                counters["dp_cache_entries"] += oracle.cache_entries
                counters["max_set_size"] = max(counters["max_set_size"], oracle.max_set_size)
                counters["total_residues"] += oracle.total_residues_stored
                counters["cache_hits"] += oracle.cache_hits
                counters["cache_misses"] += oracle.cache_misses
                if row_metrics is not None:
                    row_elapsed = time.perf_counter() - row_start
                    row_serialization_seconds = serialization_seconds - row_serialization_start
                    row_search_seconds = max(
                        0.0,
                        row_elapsed - row_factorization_seconds - row_serialization_seconds,
                    )
                    row_metrics.append(
                        {
                            "r": r,
                            "A": A,
                            "c_max": c_max,
                            "D": D,
                            "record_count": counters["records"] - row_records_start,
                            "prune_record_count": counters["prune"] - row_prune_start,
                            "leaf_record_count": counters["leaf"] - row_leaf_start,
                            "retained_cycle_count": counters["retained"] - row_retained_start,
                            "recursive_node_count": counters["recursive_nodes"] - row_nodes_start,
                            "dp_cache_entries": oracle.cache_entries,
                            "max_reachable_residue_set_size": oracle.max_set_size,
                            "total_residues_stored": oracle.total_residues_stored,
                            "dp_cache_hits": oracle.cache_hits,
                            "dp_cache_misses": oracle.cache_misses,
                            "factorization_seconds": row_factorization_seconds,
                            "search_seconds": row_search_seconds,
                            "serialization_seconds": row_serialization_seconds,
                            "wall_seconds": row_elapsed,
                            "peak_rss_kib": _peak_rss_kb(),
                            "byte_start": row_byte_start,
                            "byte_end": handle.tell(),
                            "byte_count": handle.tell() - row_byte_start,
                        }
                    )

    total_elapsed = time.perf_counter() - total_start
    search_seconds = max(0.0, total_elapsed - factorization_seconds - serialization_seconds)
    return CertificateStats(
        records=counters["records"],
        prune_records=counters["prune"],
        leaf_records=counters["leaf"],
        retained_records=counters["retained"],
        recursive_nodes_visited=counters["recursive_nodes"],
        dp_cache_entries=counters["dp_cache_entries"],
        max_reachable_residue_set_size=counters["max_set_size"],
        total_reachable_residues_stored=counters["total_residues"],
        dp_cache_hits=counters["cache_hits"],
        dp_cache_misses=counters["cache_misses"],
        factorization_seconds=factorization_seconds,
        search_seconds=search_seconds,
        serialization_seconds=serialization_seconds,
        certificate_file_size_bytes=path.stat().st_size,
        peak_rss_kb=_peak_rss_kb(),
    )


def write_row_certificate(
    path: Path,
    *,
    r: int,
    A: int,
    c_max: int,
) -> CertificateStats:
    """Write a deterministic row-level validation transcript.

    This is a benchmark artifact for final validation.  It uses the same record
    semantics as certificate v1 but covers exactly one fixed `(r, A, c_max)`
    row instead of a cumulative theorem domain.
    """
    if r <= 0 or A <= 0 or c_max <= 0:
        raise ValueError("r, A, and c_max must be positive")
    if A < A_min_for_period(r):
        raise ValueError("A must satisfy 2**A > 3**r")

    path.parent.mkdir(parents=True, exist_ok=True)
    counters = {
        "records": 0,
        "prune": 0,
        "leaf": 0,
        "retained": 0,
        "recursive_nodes": 0,
        "dp_cache_entries": 0,
        "max_set_size": 0,
        "total_residues": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }
    factorization_seconds = 0.0
    serialization_seconds = 0.0
    header = {
        "format": ROW_FORMAT,
        "row": {"r": r, "A": A, "c_max": c_max},
        "ordering": ROW_ORDERING,
        "arithmetic": ARITHMETIC,
        "purpose": "domain_validation_1_worst_row_validation",
    }

    total_start = time.perf_counter()
    with path.open("w", encoding="utf-8") as handle:
        serialization_seconds += _write_json_line(handle, header)
        D = (1 << A) - 3**r
        if D <= 0:
            raise AssertionError("declared row has nonpositive denominator")
        factor_start = time.perf_counter()
        eligible = eligible_divisors(D, c_max)
        factorization_seconds += time.perf_counter() - factor_start
        oracle = ReachableResidueOracle()
        prefix: list[int] = []

        def emit(record: dict[str, object]) -> None:
            nonlocal serialization_seconds
            serialization_seconds += _write_json_line(handle, record)
            counters["records"] += 1
            if record["kind"] == "prune":
                counters["prune"] += 1
            elif record["kind"] == "leaf":
                counters["leaf"] += 1
                if record.get("status") == "RETAINED":
                    counters["retained"] += 1

        def dfs(t: int, S: int, P: int) -> None:
            counters["recursive_nodes"] += 1
            if t == r:
                emit(_leaf_record(r, A, tuple(prefix), D, c_max))
                return
            if not prefix_can_reach_threshold(
                r=r,
                A=A,
                D=D,
                c_max=c_max,
                t=t,
                S=S,
                P=P,
                eligible=eligible,
                oracle=oracle,
            ):
                emit(
                    {
                        "kind": "prune",
                        "r": r,
                        "A": A,
                        "prefix": list(prefix),
                        "reason": "NO_ELIGIBLE_DIVISOR_REACHABLE",
                    }
                )
                return

            remaining_parts_after_next = r - (t + 1)
            if remaining_parts_after_next == 0:
                choices = range(A - S, A - S + 1)
            else:
                max_next = A - S - remaining_parts_after_next
                choices = range(1, max_next + 1)
            for next_part in choices:
                prefix.append(next_part)
                next_P = prefix_constant_after_append(r, t, S, P)
                dfs(t + 1, S + next_part, next_P)
                prefix.pop()

        dfs(0, 0, 0)
        counters["dp_cache_entries"] += oracle.cache_entries
        counters["max_set_size"] = max(counters["max_set_size"], oracle.max_set_size)
        counters["total_residues"] += oracle.total_residues_stored
        counters["cache_hits"] += oracle.cache_hits
        counters["cache_misses"] += oracle.cache_misses

    total_elapsed = time.perf_counter() - total_start
    search_seconds = max(0.0, total_elapsed - factorization_seconds - serialization_seconds)
    return CertificateStats(
        records=counters["records"],
        prune_records=counters["prune"],
        leaf_records=counters["leaf"],
        retained_records=counters["retained"],
        recursive_nodes_visited=counters["recursive_nodes"],
        dp_cache_entries=counters["dp_cache_entries"],
        max_reachable_residue_set_size=counters["max_set_size"],
        total_reachable_residues_stored=counters["total_residues"],
        dp_cache_hits=counters["cache_hits"],
        dp_cache_misses=counters["cache_misses"],
        factorization_seconds=factorization_seconds,
        search_seconds=search_seconds,
        serialization_seconds=serialization_seconds,
        certificate_file_size_bytes=path.stat().st_size,
        peak_rss_kb=_peak_rss_kb(),
    )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--r-max", type=int, default=6)
    parser.add_argument("--A-cap", type=int, default=14)
    parser.add_argument("--c-max", type=int, default=31)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("certificates/certificate_r6_A14_c31.jsonl"),
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    stats = write_certificate(
        args.output, r_max=args.r_max, A_cap=args.A_cap, c_max=args.c_max
    )
    print(f"Wrote {args.output}")
    print(
        "records={0.records}, prunes={0.prune_records}, leaves={0.leaf_records}, "
        "retained={0.retained_records}, recursive_nodes={0.recursive_nodes_visited}, "
        "dp_cache_entries={0.dp_cache_entries}, max_residue_set={0.max_reachable_residue_set_size}, "
        "file_bytes={0.certificate_file_size_bytes}".format(stats)
    )


if __name__ == "__main__":
    main()
