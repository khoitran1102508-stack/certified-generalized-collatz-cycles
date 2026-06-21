"""Reference divisor-threshold prefix sieve for valuation compositions.

This module implements the exact pruning rule specified in
``specification/divisor_threshold_sieve.md``.  For fixed ``r``, ``A`` and
``c_max``, let ``D = 2**A - 3**r`` and let

    E(D, c_max) = {g : g | D and D/g <= c_max}.

For a prefix ``p`` with length ``t``, sum ``S`` and partial constant ``P``,
the decomposition

    C_r(p || b) = P + 2**S C_m(b)

holds for suffix length ``m = r - t`` and suffix sum ``B = A - S``.  Since
``D`` is odd, every eligible ``g`` is odd and ``2**S`` is invertible modulo
``g``.  A prefix may be rejected only when, for every eligible ``g``, the
target suffix residue

    -P * 2**(-S) mod g

is absent from the exact reachable set ``R(m, B; g)``.

Soundness proof, matching the specification:

1. Any completion with normalized parameter ``c <= c_max`` has
   ``D / gcd(D, C_r(a)) <= c_max``.  Therefore some eligible divisor
   ``g in E(D, c_max)`` divides ``C_r(a)``.
2. For such a completion, ``0 == C_r(a) == P + 2**S C_m(b) (mod g)``.
   Multiplying by the inverse of ``2**S`` modulo odd ``g`` forces
   ``C_m(b)`` to equal the target suffix residue.  If that target is absent
   from ``R(m, B; g)`` for every eligible ``g``, no retained completion exists.
"""
from __future__ import annotations

import time
from dataclasses import dataclass, field
from math import comb, gcd
import sys

try:
    import resource
except ImportError:  # pragma: no cover - resource is unavailable on some platforms
    resource = None  # type: ignore[assignment]

try:
    from .core import (
        A_min_for_period,
        VerifiedCycle,
        canonical_rotation,
        cycle_constant,
        primitive_period,
        verify_candidate,
    )
    from .divisors import eligible_divisors
    from .reachable_residues import ReachableResidueOracle
except ImportError:  # direct script execution
    from core import (  # type: ignore
        A_min_for_period,
        VerifiedCycle,
        canonical_rotation,
        cycle_constant,
        primitive_period,
        verify_candidate,
    )
    from divisors import eligible_divisors  # type: ignore
    from reachable_residues import ReachableResidueOracle  # type: ignore


@dataclass
class SieveRow:
    """Deterministic counters for one fixed ``(r, A, c_max)`` row."""

    r: int
    A: int
    c_max: int
    D: int
    eligible_divisor_count: int
    total_theoretical_leaves: int
    recursive_nodes_visited: int = 0
    nodes_pruned_by_sieve: int = 0
    complete_leaves_reached: int = 0
    canonical_leaves: int = 0
    primitive_necklaces: int = 0
    retained_normalized_cycles: int = 0
    elapsed_seconds: float = 0.0
    factorization_seconds: float = 0.0
    search_seconds: float = 0.0
    dp_cache_entries: int = 0
    max_reachable_residue_set_size: int = 0
    total_reachable_residues_stored: int = 0
    dp_cache_hits: int = 0
    dp_cache_misses: int = 0
    peak_rss_kb: int = 0


@dataclass
class SieveResult:
    """Rows and retained normalized cycles from a sieve run."""

    rows: list[SieveRow] = field(default_factory=list)
    cycles: dict[tuple[int, tuple[int, ...]], VerifiedCycle] = field(
        default_factory=dict
    )


def _validate_domain(r: int, A: int, c_max: int) -> None:
    if r <= 0:
        raise ValueError("r must be positive")
    if A < r:
        raise ValueError("A must be at least r")
    if c_max <= 0:
        raise ValueError("c_max must be positive")


def _peak_rss_kb() -> int:
    """Return current process peak RSS in kilobytes when available."""
    if resource is None:
        return 0
    value = int(resource.getrusage(resource.RUSAGE_SELF).ru_maxrss)
    if sys.platform == "darwin":
        return value // 1024
    return value


def prefix_constant_after_append(r: int, t: int, S: int, P: int) -> int:
    """Return updated prefix constant after appending the next part.

    ``t`` and ``S`` describe the prefix before the append.  The new term is
    the term with index ``j=t`` in the full cycle constant.
    """
    return P + 3 ** (r - 1 - t) * (1 << S)


def prefix_can_reach_threshold(
    *,
    r: int,
    A: int,
    D: int,
    c_max: int,
    t: int,
    S: int,
    P: int,
    eligible: tuple[int, ...] | None = None,
    oracle: ReachableResidueOracle | None = None,
) -> bool:
    """Return True iff the prefix may still complete to ``c <= c_max``.

    This function implements the exact eligible-divisor and suffix-residue
    condition from the divisor-threshold sieve mathematical contract.  Returning ``False`` is
    a proof that no suffix completion of the prefix can have normalized
    parameter at or below ``c_max``.
    """
    _validate_domain(r, A, c_max)
    if D <= 0:
        raise ValueError("D must be positive")
    if not (0 <= t < r):
        raise ValueError("prefix reachability is defined only for 0 <= t < r")
    if S < t:
        raise ValueError("prefix sum is too small for positive selected parts")
    m = r - t
    B = A - S
    if B < m:
        return False

    eligible_divs = eligible if eligible is not None else eligible_divisors(D, c_max)
    if not eligible_divs:
        return False
    residue_oracle = oracle if oracle is not None else ReachableResidueOracle()

    for g in eligible_divs:
        if g == 1:
            target = 0
        else:
            inverse = pow(pow(2, S, g), -1, g)
            target = (-P * inverse) % g
        if target in residue_oracle.reachable(m, B, g):
            return True
    return False


def normalized_cycle_from_valuations(
    valuations: tuple[int, ...],
    D: int,
) -> VerifiedCycle | None:
    """Construct and verify the normalized cycle generated by valuations."""
    C = cycle_constant(valuations)
    divisor = gcd(D, C)
    c = D // divisor
    n1 = C // divisor
    verified = verify_candidate(c, valuations, n1)
    if verified is None:
        return None
    return verified


def sieve_pair(r: int, A: int, c_max: int) -> tuple[SieveRow, dict[tuple[int, tuple[int, ...]], VerifiedCycle]]:
    """Run the divisor-threshold sieve for one fixed ``(r, A, c_max)``."""
    _validate_domain(r, A, c_max)
    D = (1 << A) - 3**r
    if D <= 0:
        raise ValueError("D must be positive; choose A >= A_min_for_period(r)")
    factor_start = time.perf_counter()
    eligible = eligible_divisors(D, c_max)
    factorization_seconds = time.perf_counter() - factor_start
    oracle = ReachableResidueOracle()
    row = SieveRow(
        r=r,
        A=A,
        c_max=c_max,
        D=D,
        eligible_divisor_count=len(eligible),
        total_theoretical_leaves=comb(A - 1, r - 1),
        factorization_seconds=factorization_seconds,
    )
    retained: dict[tuple[int, tuple[int, ...]], VerifiedCycle] = {}
    prefix: list[int] = []
    start = time.perf_counter()

    def dfs(t: int, S: int, P: int) -> None:
        row.recursive_nodes_visited += 1

        if t == r:
            if S != A:
                raise AssertionError("leaf reached with wrong valuation sum")
            row.complete_leaves_reached += 1
            valuations = tuple(prefix)
            C = cycle_constant(valuations)
            c = D // gcd(D, C)
            if c > c_max:
                return
            if valuations != canonical_rotation(valuations):
                return
            row.canonical_leaves += 1
            if primitive_period(valuations) != r:
                return
            row.primitive_necklaces += 1
            cycle = normalized_cycle_from_valuations(valuations, D)
            if cycle is None:
                raise AssertionError(f"normalized candidate failed verification: {valuations}")
            if cycle.c > c_max:
                raise AssertionError("retained cycle exceeded parameter cap")
            if cycle.primitive_period != r or not cycle.essential:
                raise AssertionError("primitive normalized necklace was not essential primitive")
            retained[(cycle.c, cycle.orbit)] = cycle
            row.retained_normalized_cycles = len(retained)
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
            row.nodes_pruned_by_sieve += 1
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
    row.search_seconds = time.perf_counter() - start
    row.elapsed_seconds = row.factorization_seconds + row.search_seconds
    row.dp_cache_entries = oracle.cache_entries
    row.max_reachable_residue_set_size = oracle.max_set_size
    row.total_reachable_residues_stored = oracle.total_residues_stored
    row.dp_cache_hits = oracle.cache_hits
    row.dp_cache_misses = oracle.cache_misses
    row.peak_rss_kb = _peak_rss_kb()
    return row, retained


def run_sieve(*, r_max: int, A_cap: int, c_max: int) -> SieveResult:
    """Run the sieve over ``1 <= r <= r_max`` and admissible ``A <= A_cap``."""
    if r_max <= 0 or A_cap <= 0 or c_max <= 0:
        raise ValueError("r_max, A_cap, and c_max must be positive")
    result = SieveResult()
    for r in range(1, r_max + 1):
        amin = A_min_for_period(r)
        for A in range(amin, A_cap + 1):
            row, cycles = sieve_pair(r, A, c_max)
            result.rows.append(row)
            result.cycles.update(cycles)
    return result


def unsieved_positive_composition_dfs_pair(r: int, A: int, c_max: int) -> SieveRow:
    """Traverse the same DFS tree without prefix pruning, for benchmarking."""
    _validate_domain(r, A, c_max)
    D = (1 << A) - 3**r
    if D <= 0:
        raise ValueError("D must be positive")
    factor_start = time.perf_counter()
    eligible_count = len(eligible_divisors(D, c_max))
    factorization_seconds = time.perf_counter() - factor_start
    row = SieveRow(
        r=r,
        A=A,
        c_max=c_max,
        D=D,
        eligible_divisor_count=eligible_count,
        total_theoretical_leaves=comb(A - 1, r - 1),
        factorization_seconds=factorization_seconds,
    )
    prefix: list[int] = []
    start = time.perf_counter()

    def dfs(t: int, S: int) -> None:
        row.recursive_nodes_visited += 1
        if t == r:
            row.complete_leaves_reached += 1
            valuations = tuple(prefix)
            C = cycle_constant(valuations)
            c = D // gcd(D, C)
            if c > c_max:
                return
            if valuations != canonical_rotation(valuations):
                return
            row.canonical_leaves += 1
            if primitive_period(valuations) != r:
                return
            row.primitive_necklaces += 1
            cycle = normalized_cycle_from_valuations(valuations, D)
            if cycle is not None and cycle.c <= c_max:
                row.retained_normalized_cycles += 1
            return
        remaining_parts_after_next = r - (t + 1)
        if remaining_parts_after_next == 0:
            choices = range(A - S, A - S + 1)
        else:
            max_next = A - S - remaining_parts_after_next
            choices = range(1, max_next + 1)
        for next_part in choices:
            prefix.append(next_part)
            dfs(t + 1, S + next_part)
            prefix.pop()

    dfs(0, 0)
    row.search_seconds = time.perf_counter() - start
    row.elapsed_seconds = row.factorization_seconds + row.search_seconds
    row.peak_rss_kb = _peak_rss_kb()
    return row
