#!/usr/bin/env python3
"""Independent verifier for certificate v1 JSONL files.

This verifier intentionally imports no module from ``src``.  It reimplements
the small exact-integer formulas needed to replay the deterministic search
specified in ``docs/certificate_format.md`` and its v1 retained-record
alignment rule.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import time
from dataclasses import dataclass
from functools import reduce
from math import gcd
from pathlib import Path
from typing import Any

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on some platforms
    resource = None  # type: ignore[assignment]


FORMAT = "collatz-divisor-sieve-v1"
ORDERING = "r,A,depth-first-parts-ascending"
ARITHMETIC = "exact-integers"


class CertificateError(Exception):
    """Raised when a certificate fails deterministic replay."""


@dataclass(frozen=True)
class VerificationStats:
    """Counters collected during independent certificate replay."""

    records_seen: int
    recursive_nodes_checked: int
    prune_records_checked: int
    leaves_checked: int
    retained_cycles_checked: int
    dp_cache_entries: int
    max_reachable_residue_set_size: int
    total_reachable_residues_stored: int
    dp_cache_hits: int
    dp_cache_misses: int
    elapsed_seconds: float
    peak_rss_kib: int

    def __bool__(self) -> bool:
        return True


def peak_rss_kib() -> int:
    """Return current process peak RSS in KiB when available."""
    if resource is None:
        return 0
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return value // 1024
    return value


def v2(n: int) -> int:
    if n <= 0:
        raise ValueError("v2 expects a positive integer")
    return (n & -n).bit_length() - 1


def rotate(seq: tuple[int, ...], offset: int) -> tuple[int, ...]:
    if not seq:
        return seq
    offset %= len(seq)
    return seq[offset:] + seq[:offset]


def canonical_rotation(seq: tuple[int, ...]) -> tuple[int, ...]:
    return min(rotate(seq, i) for i in range(len(seq))) if seq else seq


def canonical_cycle_and_valuations(
    orbit: tuple[int, ...], valuations: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...]]:
    return min((rotate(orbit, i), rotate(valuations, i)) for i in range(len(orbit)))


def canonical_cycle_valuations_and_offset(
    orbit: tuple[int, ...], valuations: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    return min(
        (rotate(orbit, i), rotate(valuations, i), i)
        for i in range(len(orbit))
    )


def primitive_period(seq: tuple[int, ...]) -> int:
    n = len(seq)
    for period in range(1, n + 1):
        if n % period == 0 and all(seq[i] == seq[i % period] for i in range(n)):
            return period
    return n


def A_min_for_period(r: int) -> int:
    return (3**r).bit_length()


def cycle_constant(valuations: tuple[int, ...]) -> int:
    r = len(valuations)
    total = 0
    prefix = 0
    for j in range(r):
        if j:
            prefix += valuations[j - 1]
        total += 3 ** (r - 1 - j) * (1 << prefix)
    return total


def hash_payload(payload: Any) -> str:
    """Return the canonical JSON SHA-256 used for semantic cycle digests."""

    encoded = json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()
    return hashlib.sha256(encoded).hexdigest()


def divisors(n: int) -> tuple[int, ...]:
    if n <= 0:
        raise ValueError("n must be positive")
    small: list[int] = []
    large: list[int] = []
    d = 1
    while d * d <= n:
        if n % d == 0:
            small.append(d)
            if d * d != n:
                large.append(n // d)
        d += 1
    return tuple(small + large[::-1])


def eligible_divisors(D: int, c_max: int) -> tuple[int, ...]:
    return tuple(g for g in divisors(D) if D // g <= c_max)


class ResidueOracle:
    def __init__(self) -> None:
        self.cache: dict[tuple[int, int, int], frozenset[int]] = {}
        self.max_set_size = 0
        self.total_residues_stored = 0
        self.cache_hits = 0
        self.cache_misses = 0

    def reachable(self, m: int, B: int, g: int) -> frozenset[int]:
        if m <= 0 or B < m or g <= 0 or g % 2 == 0:
            raise ValueError("invalid reachable-residue state")
        key = (m, B, g)
        if key in self.cache:
            self.cache_hits += 1
            return self.cache[key]
        self.cache_misses += 1
        if m == 1:
            result = frozenset({1 % g})
        else:
            residues: set[int] = set()
            constant = pow(3, m - 1, g)
            for first in range(1, B - m + 2):
                multiplier = pow(2, first, g)
                for tail in self.reachable(m - 1, B - first, g):
                    residues.add((constant + multiplier * tail) % g)
            result = frozenset(residues)
        self.cache[key] = result
        self.total_residues_stored += len(result)
        if len(result) > self.max_set_size:
            self.max_set_size = len(result)
        return result


def prefix_constant_after_append(r: int, t: int, S: int, P: int) -> int:
    return P + 3 ** (r - 1 - t) * (1 << S)


def prefix_can_reach(
    *,
    r: int,
    A: int,
    D: int,
    c_max: int,
    t: int,
    S: int,
    P: int,
    eligible: tuple[int, ...],
    oracle: ResidueOracle,
) -> bool:
    m = r - t
    B = A - S
    if B < m or not eligible:
        return False
    for g in eligible:
        if g == 1:
            target = 0
        else:
            target = (-P * pow(pow(2, S, g), -1, g)) % g
        if target in oracle.reachable(m, B, g):
            return True
    return False


def verify_candidate(
    c: int, valuations: tuple[int, ...], n1: int
) -> tuple[int, tuple[int, ...]] | None:
    if c <= 0 or c % 2 == 0 or n1 <= 0 or n1 % 2 == 0:
        return None
    orbit = [n1]
    for i, expected in enumerate(valuations):
        current = orbit[i]
        if current <= 0 or current % 2 == 0:
            return None
        x = 3 * current + c
        actual = v2(x)
        if actual != expected:
            return None
        nxt = x >> actual
        if i < len(valuations) - 1:
            if nxt <= 0 or nxt % 2 == 0:
                return None
            orbit.append(nxt)
        elif nxt != n1:
            return None
    orbit_tuple = tuple(orbit)
    canonical_orbit, _ = canonical_cycle_and_valuations(orbit_tuple, valuations)
    shared = reduce(gcd, (c, *canonical_orbit))
    if shared != 1:
        return None
    if primitive_period(canonical_orbit) != len(valuations):
        return None
    return c, canonical_orbit


def _positive_int_tuple(value: Any, field: str) -> tuple[int, ...]:
    if not isinstance(value, list) or not value:
        raise CertificateError(f"{field} must be a nonempty list")
    result: list[int] = []
    for item in value:
        if not isinstance(item, int) or item <= 0:
            raise CertificateError(f"{field} must contain positive integers")
        result.append(item)
    return tuple(result)


def _raw_orbit_from_search(
    c: int, search_valuations: tuple[int, ...], n1: int
) -> tuple[int, ...]:
    orbit = [n1]
    for index, expected in enumerate(search_valuations):
        current = orbit[index]
        if current <= 0 or current % 2 == 0:
            raise CertificateError("raw orbit contains a nonpositive or even value")
        value = 3 * current + c
        actual = v2(value)
        if actual != expected:
            raise CertificateError("search_valuations do not match raw reconstructed orbit")
        nxt = value >> actual
        if index < len(search_valuations) - 1:
            if nxt <= 0 or nxt % 2 == 0:
                raise CertificateError("raw orbit next value is nonpositive or even")
            orbit.append(nxt)
        elif nxt != n1:
            raise CertificateError("raw reconstructed orbit does not close")
    return tuple(orbit)


def _validate_stored_cycle_pair(
    *,
    c: int,
    orbit: tuple[int, ...],
    cycle_valuations: tuple[int, ...],
) -> None:
    if c <= 0 or c % 2 == 0:
        raise CertificateError("retained c must be positive odd")
    if len(orbit) != len(cycle_valuations):
        raise CertificateError("orbit and cycle_valuations lengths differ")
    r = len(orbit)
    if r == 0:
        raise CertificateError("retained orbit may not be empty")
    for index, current in enumerate(orbit):
        if current <= 0 or current % 2 == 0:
            raise CertificateError("retained orbit contains a nonpositive or even value")
        value = 3 * current + c
        actual = v2(value)
        if actual != cycle_valuations[index]:
            raise CertificateError(
                "stored orbit/cycle_valuations alignment failure at index "
                f"{index}: expected {actual}, got {cycle_valuations[index]}"
            )
        nxt = value >> actual
        if nxt != orbit[(index + 1) % r]:
            raise CertificateError(
                "stored orbit transition failure at index "
                f"{index}: got {nxt}, expected {orbit[(index + 1) % r]}"
            )


def _retained_leaf_record(
    r: int,
    A: int,
    search_valuations: tuple[int, ...],
    D: int,
    c_max: int,
) -> dict[str, Any]:
    C = cycle_constant(search_valuations)
    divisor = gcd(D, C)
    c = D // divisor
    n1 = C // divisor
    if c <= 0 or c > c_max:
        raise CertificateError("retained parameter is outside the declared cap")
    raw_orbit = _raw_orbit_from_search(c, search_valuations, n1)
    canonical_orbit, cycle_valuations, offset = canonical_cycle_valuations_and_offset(
        raw_orbit, search_valuations
    )
    _validate_stored_cycle_pair(
        c=c, orbit=canonical_orbit, cycle_valuations=cycle_valuations
    )
    if sum(cycle_valuations) != A:
        raise CertificateError("cycle_valuations have wrong total valuation")
    shared = reduce(gcd, (c, *canonical_orbit))
    if shared != 1:
        raise CertificateError("retained cycle is not essential")
    if primitive_period(canonical_orbit) != r:
        raise CertificateError("retained cycle has nonprimitive orbit period")
    return {
        "A": A,
        "c": c,
        "canonical_offset": offset,
        "cycle_valuations": list(cycle_valuations),
        "kind": "leaf",
        "orbit": list(canonical_orbit),
        "r": r,
        "search_valuations": list(search_valuations),
        "status": "RETAINED",
    }


def validate_retained_record(record: dict[str, Any]) -> None:
    """Validate the exact serialized retained orbit/cycle_valuations pair."""

    try:
        r = record["r"]
        A = record["A"]
        c = record["c"]
        offset = record["canonical_offset"]
    except KeyError as exc:
        raise CertificateError(f"retained record missing field {exc.args[0]}") from exc
    if not isinstance(r, int) or r <= 0:
        raise CertificateError("retained r must be positive")
    if not isinstance(A, int) or A <= 0:
        raise CertificateError("retained A must be positive")
    if not isinstance(c, int) or c <= 0:
        raise CertificateError("retained c must be positive")
    if not isinstance(offset, int) or not (0 <= offset < r):
        raise CertificateError("canonical_offset is outside the retained period")
    search_valuations = _positive_int_tuple(
        record.get("search_valuations"), "search_valuations"
    )
    cycle_valuations = _positive_int_tuple(
        record.get("cycle_valuations"), "cycle_valuations"
    )
    orbit = _positive_int_tuple(record.get("orbit"), "orbit")
    if len(search_valuations) != r:
        raise CertificateError("search_valuations length does not equal r")
    if len(cycle_valuations) != r:
        raise CertificateError("cycle_valuations length does not equal r")
    if len(orbit) != r:
        raise CertificateError("orbit length does not equal r")
    if sum(search_valuations) != A or sum(cycle_valuations) != A:
        raise CertificateError("valuation totals do not equal A")
    _validate_stored_cycle_pair(c=c, orbit=orbit, cycle_valuations=cycle_valuations)
    D = (1 << A) - 3**r
    if D <= 0:
        raise CertificateError("retained record has nonpositive denominator")
    C = cycle_constant(search_valuations)
    divisor = gcd(D, C)
    if c != D // divisor:
        raise CertificateError("retained c does not match search_valuations")
    raw_orbit = _raw_orbit_from_search(c, search_valuations, C // divisor)
    expected_orbit, expected_cycle_valuations, expected_offset = (
        canonical_cycle_valuations_and_offset(raw_orbit, search_valuations)
    )
    if orbit != expected_orbit:
        raise CertificateError("serialized orbit is not the canonical raw orbit")
    if cycle_valuations != expected_cycle_valuations:
        raise CertificateError("serialized cycle_valuations are not canonically aligned")
    if offset != expected_offset:
        raise CertificateError("canonical_offset does not match the shared rotation")
    if primitive_period(orbit) != r:
        raise CertificateError("serialized orbit is not primitive of declared length")
    if reduce(gcd, (c, *orbit)) != 1:
        raise CertificateError("serialized retained cycle is not essential")


def cycle_payload_from_retained(record: dict[str, Any]) -> dict[str, Any]:
    """Return the normalized semantic cycle payload for a retained record."""

    return {
        "A": record["A"],
        "c": record["c"],
        "essential": True,
        "orbit": record["orbit"],
        "primitive_period": len(record["orbit"]),
        "r": record["r"],
        "valuations": record["cycle_valuations"],
    }


def expected_leaf_record(
    r: int, A: int, search_valuations: tuple[int, ...], D: int, c_max: int
) -> dict[str, Any]:
    C = cycle_constant(search_valuations)
    c = D // gcd(D, C)
    record: dict[str, Any] = {
        "A": A,
        "kind": "leaf",
        "r": r,
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
    return _retained_leaf_record(r, A, search_valuations, D, c_max)


class JsonlRecordStream:
    """Strict streaming JSONL reader for deterministic certificate replay."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.handle = None
        self.line_number = 0
        self.records_seen = 0

    def __enter__(self) -> "JsonlRecordStream":
        self.handle = self.path.open("r", encoding="utf-8")
        return self

    def __exit__(self, *args: object) -> None:
        if self.handle is not None:
            self.handle.close()

    def _readline(self) -> str:
        if self.handle is None:
            raise RuntimeError("stream is not open")
        line = self.handle.readline()
        if line:
            self.line_number += 1
        return line

    def _parse_object(self, line: str, role: str) -> dict[str, Any]:
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise CertificateError(
                f"invalid JSON {role} at line {self.line_number}: {exc}"
            ) from exc
        if not isinstance(payload, dict):
            raise CertificateError(f"{role} at line {self.line_number} must be a JSON object")
        return payload

    def read_header(self) -> dict[str, Any]:
        line = self._readline()
        if not line:
            raise CertificateError("empty certificate")
        return self._parse_object(line, "header")

    def next_record(self) -> dict[str, Any] | None:
        line = self._readline()
        if not line:
            return None
        self.records_seen += 1
        return self._parse_object(line, "record")

    def require_exhausted(self) -> None:
        line = self._readline()
        if line:
            raise CertificateError(
                f"extra certificate records starting at index {self.records_seen}"
            )


def _check_expected_domain(
    domain: dict[str, Any],
    *,
    expected_r_max: int | None,
    expected_A_cap: int | None,
    expected_c_max: int | None,
) -> None:
    if expected_r_max is not None and domain.get("r_max") != expected_r_max:
        raise CertificateError(
            f"r_max mismatch: expected {expected_r_max}, got {domain.get('r_max')}"
        )
    if expected_A_cap is not None and domain.get("A_cap") != expected_A_cap:
        raise CertificateError(
            f"A_cap mismatch: expected {expected_A_cap}, got {domain.get('A_cap')}"
        )
    if expected_c_max is not None and domain.get("c_max") != expected_c_max:
        raise CertificateError(
            f"c_max mismatch: expected {expected_c_max}, got {domain.get('c_max')}"
        )


def verify_certificate_file(
    path: Path,
    *,
    expected_r_max: int | None = None,
    expected_A_cap: int | None = None,
    expected_c_max: int | None = None,
) -> VerificationStats:
    """Replay ``path`` and return counters if it is a valid certificate-v1 file."""
    started = time.perf_counter()
    stream = JsonlRecordStream(path)
    stream.__enter__()
    try:
        header = stream.read_header()
    except Exception:
        stream.__exit__(None, None, None)
        raise
    if header.get("format") != FORMAT:
        stream.__exit__(None, None, None)
        raise CertificateError("unexpected certificate format")
    if header.get("ordering") != ORDERING:
        stream.__exit__(None, None, None)
        raise CertificateError("unexpected ordering")
    if header.get("arithmetic") != ARITHMETIC:
        stream.__exit__(None, None, None)
        raise CertificateError("unexpected arithmetic declaration")
    domain = header.get("domain")
    if not isinstance(domain, dict):
        stream.__exit__(None, None, None)
        raise CertificateError("missing domain object")
    r_max = domain.get("r_max")
    A_cap = domain.get("A_cap")
    c_max = domain.get("c_max")
    if not all(isinstance(x, int) and x > 0 for x in (r_max, A_cap, c_max)):
        stream.__exit__(None, None, None)
        raise CertificateError("invalid domain")
    try:
        _check_expected_domain(
            domain,
            expected_r_max=expected_r_max,
            expected_A_cap=expected_A_cap,
            expected_c_max=expected_c_max,
        )
    except Exception:
        stream.__exit__(None, None, None)
        raise

    stats = {
        "nodes": 0,
        "prunes": 0,
        "leaves": 0,
        "retained": 0,
        "dp_cache_entries": 0,
        "max_set_size": 0,
        "total_residues": 0,
        "cache_hits": 0,
        "cache_misses": 0,
    }
    retained_cycle_payloads: list[dict[str, Any]] = []

    def require(expected: dict[str, Any]) -> None:
        actual = stream.next_record()
        if actual is None:
            raise CertificateError(f"missing record: expected {expected}")
        if actual.get("kind") == "leaf" and actual.get("status") == "RETAINED":
            validate_retained_record(actual)
        if actual != expected:
            index = stream.records_seen - 1
            raise CertificateError(
                f"record mismatch at index {index}: expected {expected}, got {actual}"
            )
        if expected.get("kind") == "leaf" and expected.get("status") == "RETAINED":
            retained_cycle_payloads.append(cycle_payload_from_retained(expected))

    try:
        for r in range(1, r_max + 1):
            for A in range(A_min_for_period(r), A_cap + 1):
                D = (1 << A) - 3**r
                if D <= 0:
                    raise CertificateError("invalid denominator in declared domain")
                eligible = eligible_divisors(D, c_max)
                oracle = ResidueOracle()
                prefix: list[int] = []

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
                stats["dp_cache_entries"] += len(oracle.cache)
                stats["max_set_size"] = max(stats["max_set_size"], oracle.max_set_size)
                stats["total_residues"] += oracle.total_residues_stored
                stats["cache_hits"] += oracle.cache_hits
                stats["cache_misses"] += oracle.cache_misses

        stream.require_exhausted()
        declared_digest = header.get("normalized_cycle_set_sha256")
        if declared_digest is not None:
            if not isinstance(declared_digest, str):
                raise CertificateError("declared normalized cycle-set digest must be a string")
            retained_cycle_payloads.sort(
                key=lambda item: (item["c"], item["r"], item["A"], item["orbit"])
            )
            actual_digest = hash_payload(retained_cycle_payloads)
            if actual_digest != declared_digest:
                raise CertificateError(
                    "normalized cycle-set digest mismatch: "
                    f"expected {declared_digest}, got {actual_digest}"
                )
        return VerificationStats(
            records_seen=stream.records_seen,
            recursive_nodes_checked=stats["nodes"],
            prune_records_checked=stats["prunes"],
            leaves_checked=stats["leaves"],
            retained_cycles_checked=stats["retained"],
            dp_cache_entries=stats["dp_cache_entries"],
            max_reachable_residue_set_size=stats["max_set_size"],
            total_reachable_residues_stored=stats["total_residues"],
            dp_cache_hits=stats["cache_hits"],
            dp_cache_misses=stats["cache_misses"],
            elapsed_seconds=time.perf_counter() - started,
            peak_rss_kib=peak_rss_kib(),
        )
    finally:
        stream.__exit__(None, None, None)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("certificate", type=Path)
    parser.add_argument("--expect-r-max", type=int)
    parser.add_argument("--expect-A-cap", type=int)
    parser.add_argument("--expect-c-max", type=int)
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    try:
        stats = verify_certificate_file(
            args.certificate,
            expected_r_max=args.expect_r_max,
            expected_A_cap=args.expect_A_cap,
            expected_c_max=args.expect_c_max,
        )
    except CertificateError as exc:
        print(f"INVALID: {exc}")
        raise SystemExit(1) from exc
    print("VALID")
    print(
        "records={0.records_seen}, recursive_nodes={0.recursive_nodes_checked}, "
        "prunes={0.prune_records_checked}, leaves={0.leaves_checked}, "
        "retained={0.retained_cycles_checked}, dp_cache_entries={0.dp_cache_entries}, "
        "max_residue_set={0.max_reachable_residue_set_size}, elapsed_seconds={0.elapsed_seconds:.6f}, "
        "peak_rss_kib={0.peak_rss_kib}".format(
            stats
        )
    )


if __name__ == "__main__":
    main()
