"""Exact integer factorization and divisor utilities.

The divisor-threshold sieve needs the eligible divisors

    E(D, c_max) = {g : g | D and D / g <= c_max}.

All functions in this module use deterministic trial division and Python
integers only.  The implementation is intentionally small and auditable; the
divisor-threshold sieve benchmark domains use modest odd denominators.
"""
from __future__ import annotations

from collections.abc import Iterator


def factorize(n: int) -> dict[int, int]:
    """Return the prime factorization of a positive integer.

    Parameters
    ----------
    n:
        Positive integer to factor.

    Returns
    -------
    dict[int, int]
        Mapping ``prime -> exponent`` in increasing prime order.
    """
    if n <= 0:
        raise ValueError("n must be a positive integer")
    factors: dict[int, int] = {}
    remaining = n
    exponent = 0
    while remaining % 2 == 0:
        remaining //= 2
        exponent += 1
    if exponent:
        factors[2] = exponent

    p = 3
    while p * p <= remaining:
        exponent = 0
        while remaining % p == 0:
            remaining //= p
            exponent += 1
        if exponent:
            factors[p] = exponent
        p += 2
    if remaining > 1:
        factors[remaining] = 1
    return factors


def divisors_from_factorization(factors: dict[int, int]) -> tuple[int, ...]:
    """Enumerate all positive divisors from a prime factorization."""
    divisors = [1]
    for prime in sorted(factors):
        exponent = factors[prime]
        if prime <= 1 or exponent <= 0:
            raise ValueError("factorization must use primes with positive exponents")
        powers = [prime**k for k in range(1, exponent + 1)]
        divisors += [d * power for d in divisors for power in powers]
    return tuple(sorted(divisors))


def divisors(n: int) -> tuple[int, ...]:
    """Return all positive divisors of ``n`` in increasing order."""
    return divisors_from_factorization(factorize(n))


def eligible_divisors(D: int, c_max: int) -> tuple[int, ...]:
    """Return eligible divisors ``g`` with ``g | D`` and ``D // g <= c_max``.

    This is exactly the set ``E(D, c_max)`` in
    ``specification/divisor_threshold_sieve.md``.  If the returned tuple is
    empty then no valuation completion can have normalized parameter at most
    ``c_max``.
    """
    if D <= 0:
        raise ValueError("D must be a positive integer")
    if c_max <= 0:
        raise ValueError("c_max must be a positive integer")
    return tuple(g for g in divisors(D) if D // g <= c_max)


def iter_divisors(n: int) -> Iterator[int]:
    """Yield all positive divisors of ``n`` in increasing order."""
    yield from divisors(n)
