#!/usr/bin/env python3
"""Independent streaming verifier for final validation/Final certificate row transcripts.

This script imports no production ``src`` modules.  It reuses the independent
exact arithmetic helpers from ``verifier.verify_certificate`` and verifies a
single fixed-row transcript with the same record semantics as certificate v1.
"""
from __future__ import annotations

import argparse
import time
from pathlib import Path
from typing import Any

try:
    from .verify_certificate import (
        ARITHMETIC,
        CertificateError,
        JsonlRecordStream,
        ResidueOracle,
        VerificationStats,
        eligible_divisors,
        expected_leaf_record,
        peak_rss_kib,
        prefix_can_reach,
        prefix_constant_after_append,
    )
except ImportError:  # direct script execution
    from verify_certificate import (  # type: ignore
        ARITHMETIC,
        CertificateError,
        JsonlRecordStream,
        ResidueOracle,
        VerificationStats,
        eligible_divisors,
        expected_leaf_record,
        peak_rss_kib,
        prefix_can_reach,
        prefix_constant_after_append,
    )


ROW_FORMAT = "collatz-divisor-sieve-row-v1"
ROW_ORDERING = "single-row,depth-first-parts-ascending"


def _check_expected(row: dict[str, Any], r: int | None, A: int | None, c_max: int | None) -> None:
    if r is not None and row.get("r") != r:
        raise CertificateError(f"row r mismatch: expected {r}, got {row.get('r')}")
    if A is not None and row.get("A") != A:
        raise CertificateError(f"row A mismatch: expected {A}, got {row.get('A')}")
    if c_max is not None and row.get("c_max") != c_max:
        raise CertificateError(
            f"row c_max mismatch: expected {c_max}, got {row.get('c_max')}"
        )


def verify_row_certificate_file(
    path: Path,
    *,
    expected_r: int | None = None,
    expected_A: int | None = None,
    expected_c_max: int | None = None,
) -> VerificationStats:
    """Replay a single-row validation transcript in deterministic order."""
    started = time.perf_counter()
    with JsonlRecordStream(path) as stream:
        header = stream.read_header()
        if header.get("format") != ROW_FORMAT:
            raise CertificateError("unexpected row certificate format")
        if header.get("ordering") != ROW_ORDERING:
            raise CertificateError("unexpected row ordering")
        if header.get("arithmetic") != ARITHMETIC:
            raise CertificateError("unexpected arithmetic declaration")
        row = header.get("row")
        if not isinstance(row, dict):
            raise CertificateError("missing row object")
        r = row.get("r")
        A = row.get("A")
        c_max = row.get("c_max")
        if not all(isinstance(x, int) and x > 0 for x in (r, A, c_max)):
            raise CertificateError("invalid row declaration")
        _check_expected(row, expected_r, expected_A, expected_c_max)

        D = (1 << A) - 3**r
        if D <= 0:
            raise CertificateError("invalid denominator in declared row")
        eligible = eligible_divisors(D, c_max)
        oracle = ResidueOracle()
        prefix: list[int] = []
        stats = {
            "nodes": 0,
            "prunes": 0,
            "leaves": 0,
            "retained": 0,
        }

        def require(expected: dict[str, Any]) -> None:
            actual = stream.next_record()
            if actual is None:
                raise CertificateError(f"missing record: expected {expected}")
            if actual != expected:
                index = stream.records_seen - 1
                raise CertificateError(
                    f"record mismatch at index {index}: expected {expected}, got {actual}"
                )

        def dfs(t: int, S: int, P: int) -> None:
            stats["nodes"] += 1
            if t == r:
                expected = expected_leaf_record(r, A, tuple(prefix), D, c_max)
                stats["leaves"] += 1
                if expected.get("status") == "RETAINED":
                    stats["retained"] += 1
                require(expected)
                return
            if not prefix_can_reach(
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
                stats["prunes"] += 1
                require(
                    {
                        "A": A,
                        "kind": "prune",
                        "prefix": list(prefix),
                        "r": r,
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
        stream.require_exhausted()
        return VerificationStats(
            records_seen=stream.records_seen,
            recursive_nodes_checked=stats["nodes"],
            prune_records_checked=stats["prunes"],
            leaves_checked=stats["leaves"],
            retained_cycles_checked=stats["retained"],
            dp_cache_entries=len(oracle.cache),
            max_reachable_residue_set_size=oracle.max_set_size,
            total_reachable_residues_stored=oracle.total_residues_stored,
            dp_cache_hits=oracle.cache_hits,
            dp_cache_misses=oracle.cache_misses,
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_kib=peak_rss_kib(),
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--expect-r", type=int)
    parser.add_argument("--expect-A", type=int)
    parser.add_argument("--expect-c-max", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        stats = verify_row_certificate_file(
            args.certificate,
            expected_r=args.expect_r,
            expected_A=args.expect_A,
            expected_c_max=args.expect_c_max,
        )
    except CertificateError as exc:
        print(f"INVALID_ROW: {exc}")
        raise SystemExit(1) from exc
    print("VALID_ROW")
    print(
        "records={0.records_seen}, recursive_nodes={0.recursive_nodes_checked}, "
        "prunes={0.prune_records_checked}, leaves={0.leaves_checked}, "
        "retained={0.retained_cycles_checked}, dp_cache_entries={0.dp_cache_entries}, "
        "max_residue_set={0.max_reachable_residue_set_size}, "
        "total_residues={0.total_reachable_residues_stored}, "
        "elapsed_seconds={0.elapsed_seconds:.6f}, peak_rss_kib={0.peak_rss_kib}".format(
            stats
        )
    )


if __name__ == "__main__":
    main()
