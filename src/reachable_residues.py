"""Exact suffix reachable-residue sets for the divisor-threshold sieve.

For positive suffix compositions ``b`` of ``B`` into ``m`` parts, define

    C_m(b) = sum_{j=0}^{m-1} 3**(m-1-j) * 2**(b_1 + ... + b_j).

The divisor-threshold sieve pruning rule needs the exact set

    R(m, B; g) = {C_m(b) mod g}.

This module implements both a brute-force enumerator and the memoized
recurrence from ``specification/divisor_threshold_sieve.md``.  No sampling or
probabilistic data structure is used.
"""
from __future__ import annotations

from dataclasses import dataclass, field

try:
    from .core import compositions, cycle_constant
except ImportError:  # direct script execution
    from core import compositions, cycle_constant  # type: ignore


def _validate_state(m: int, B: int, g: int) -> None:
    if m <= 0:
        raise ValueError("m must be positive")
    if B < m:
        raise ValueError("B must be at least m for positive suffix parts")
    if g <= 0 or g % 2 == 0:
        raise ValueError("g must be a positive odd modulus")


def brute_force_reachable_residues(m: int, B: int, g: int) -> frozenset[int]:
    """Compute ``R(m, B; g)`` by direct suffix composition enumeration."""
    _validate_state(m, B, g)
    return frozenset(cycle_constant(suffix) % g for suffix in compositions(B, m))


@dataclass
class ReachableResidueOracle:
    """Memoized exact implementation of the reachable-residue recurrence.

    The counters are instrumentation only.  They do not alter the recurrence
    or any pruning decision.
    """

    cache: dict[tuple[int, int, int], frozenset[int]] = field(default_factory=dict)
    max_set_size: int = 0
    cache_hits: int = 0
    cache_misses: int = 0
    total_residues_stored: int = 0

    def reachable(self, m: int, B: int, g: int) -> frozenset[int]:
        """Return the exact reachable-residue set ``R(m, B; g)``.

        The recurrence is

        ``R(1, B; g) = {1 mod g}``,

        and, for ``m >= 2``,

        ``R(m,B;g) = union_x {3**(m-1) + 2**x y mod g:
        y in R(m-1,B-x;g)}``,

        where ``1 <= x <= B-m+1``.
        """
        _validate_state(m, B, g)
        key = (m, B, g)
        cached = self.cache.get(key)
        if cached is not None:
            self.cache_hits += 1
            return cached
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

    @property
    def cache_entries(self) -> int:
        """Number of memoized ``(m, B, g)`` states."""
        return len(self.cache)


def reachable_residues(m: int, B: int, g: int) -> frozenset[int]:
    """Convenience wrapper around ``ReachableResidueOracle``."""
    return ReachableResidueOracle().reachable(m, B, g)
