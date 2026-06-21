#!/usr/bin/env python3
"""Exact arithmetic core for generalized accelerated odd Collatz maps.

For positive odd c and positive odd n, define

    U_c(n) = (3n+c) / 2**v2(3n+c).

A length-r valuation vector a=(a_1,...,a_r), A=sum(a_i), satisfies

    (2**A - 3**r) n_1 = c C(a),

where

    C(a) = sum_{j=0}^{r-1} 3**(r-1-j) 2**(a_1+...+a_j),

with the empty prefix sum equal to zero.
"""
from __future__ import annotations

from dataclasses import dataclass
from functools import reduce
from math import gcd
from typing import Iterable, Iterator, Sequence


def v2(n: int) -> int:
    """Return the exact 2-adic valuation of a positive integer."""
    if n <= 0:
        raise ValueError("v2 expects a positive integer")
    return (n & -n).bit_length() - 1


def odd_map(n: int, c: int) -> int:
    """Apply U_c to a positive odd integer n."""
    if n <= 0 or n % 2 == 0:
        raise ValueError("n must be a positive odd integer")
    if c <= 0 or c % 2 == 0:
        raise ValueError("c must be a positive odd integer")
    x = 3 * n + c
    return x >> v2(x)


def rotate(seq: tuple[int, ...], offset: int) -> tuple[int, ...]:
    if not seq:
        return seq
    offset %= len(seq)
    return seq[offset:] + seq[:offset]


def rotations(seq: tuple[int, ...]) -> Iterator[tuple[int, ...]]:
    for i in range(len(seq)):
        yield rotate(seq, i)


def canonical_rotation(seq: tuple[int, ...]) -> tuple[int, ...]:
    if not seq:
        return seq
    return min(rotations(seq))


def canonical_cycle_and_valuations(
    orbit: tuple[int, ...], valuations: tuple[int, ...]
) -> tuple[tuple[int, ...], tuple[int, ...], int]:
    """Canonicalize an orbit and its valuations using one shared offset.

    The lexicographically least (rotated orbit, rotated valuations) pair is
    selected. Returning the offset makes the alignment auditable.
    """
    if len(orbit) != len(valuations) or not orbit:
        raise ValueError("orbit and valuations must have the same nonzero length")
    candidates = [
        (rotate(orbit, i), rotate(valuations, i), i) for i in range(len(orbit))
    ]
    return min(candidates, key=lambda item: (item[0], item[1]))


def primitive_period(seq: Sequence[int]) -> int:
    """Return the least period of a finite sequence."""
    n = len(seq)
    if n == 0:
        return 0
    for period in range(1, n + 1):
        if n % period == 0 and all(seq[i] == seq[i % period] for i in range(n)):
            return period
    return n


def compositions(total: int, parts: int) -> Iterable[tuple[int, ...]]:
    """Yield all ordered compositions of total into positive parts."""
    if total < parts or parts <= 0:
        return
    if parts == 1:
        yield (total,)
        return
    for first in range(1, total - parts + 2):
        for rest in compositions(total - first, parts - 1):
            yield (first,) + rest


def A_min_for_period(r: int) -> int:
    """Least A for which 2**A > 3**r, using exact arithmetic."""
    if r <= 0:
        raise ValueError("r must be positive")
    return (3**r).bit_length()


def A_max_general(c: int, r: int) -> int:
    """General positive-cycle upper bound A <= floor(log2((3+c)**r)).

    It follows from 2**A = product_i (3+c/n_i) <= (3+c)**r.
    This bound can be very large; practical searches should normally provide
    an explicit A cap and state it as part of the search domain.
    """
    if c <= 0 or c % 2 == 0 or r <= 0:
        raise ValueError("c must be positive odd and r must be positive")
    return ((3 + c) ** r).bit_length() - 1


def cycle_constant(valuations: tuple[int, ...]) -> int:
    """Compute C(a) in the generalized cycle identity."""
    r = len(valuations)
    if r == 0 or any(a <= 0 for a in valuations):
        raise ValueError("valuations must be a nonempty tuple of positive integers")
    total = 0
    prefix = 0
    for j in range(r):
        if j:
            prefix += valuations[j - 1]
        total += 3 ** (r - 1 - j) * (1 << prefix)
    return total


def candidate_start(c: int, valuations: tuple[int, ...]) -> int | None:
    """Recover n_1 from a valuation vector, or return None if nonintegral."""
    r = len(valuations)
    A = sum(valuations)
    denominator = (1 << A) - 3**r
    if denominator <= 0:
        return None
    numerator = c * cycle_constant(valuations)
    quotient, remainder = divmod(numerator, denominator)
    if remainder:
        return None
    return quotient


@dataclass(frozen=True)
class VerifiedCycle:
    c: int
    orbit: tuple[int, ...]
    valuations: tuple[int, ...]
    A: int
    primitive_period: int
    essential: bool
    shared_gcd: int
    canonical_offset: int


def verify_candidate(
    c: int, valuations: tuple[int, ...], n1: int
) -> VerifiedCycle | None:
    """Independently reconstruct and verify a candidate cycle exactly."""
    if c <= 0 or c % 2 == 0:
        raise ValueError("c must be a positive odd integer")
    if n1 <= 0 or n1 % 2 == 0:
        return None
    if not valuations or any(a <= 0 for a in valuations):
        return None

    r = len(valuations)
    orbit = [n1]
    for i, expected_a in enumerate(valuations):
        current = orbit[i]
        if current <= 0 or current % 2 == 0:
            return None
        x = 3 * current + c
        actual_a = v2(x)
        if actual_a != expected_a:
            return None
        nxt = x >> actual_a
        if i < r - 1:
            if nxt <= 0 or nxt % 2 == 0:
                return None
            orbit.append(nxt)
        elif nxt != n1:
            return None

    orbit_tuple = tuple(orbit)
    if any(odd_map(orbit_tuple[i], c) != orbit_tuple[(i + 1) % r] for i in range(r)):
        return None

    canonical_orbit, canonical_valuations, offset = canonical_cycle_and_valuations(
        orbit_tuple, valuations
    )
    shared_gcd = reduce(gcd, (c, *canonical_orbit))
    return VerifiedCycle(
        c=c,
        orbit=canonical_orbit,
        valuations=canonical_valuations,
        A=sum(valuations),
        primitive_period=primitive_period(canonical_orbit),
        essential=(shared_gcd == 1),
        shared_gcd=shared_gcd,
        canonical_offset=offset,
    )


def is_normalized_parameter(c: int) -> bool:
    """Return True for the primary essential-cycle parameter set.

    If 3 divides c, every image under U_c is divisible by 3. Hence any cycle
    has gcd at least 3 with c and is inherited rather than essential.
    """
    return c > 0 and c % 2 == 1 and c % 3 != 0
