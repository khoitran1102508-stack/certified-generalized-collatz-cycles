from math import gcd

from src.core import A_min_for_period, compositions, cycle_constant
from src.divisor_sieve import (
    prefix_can_reach_threshold,
    prefix_constant_after_append,
)
from src.divisors import eligible_divisors
from src.reachable_residues import ReachableResidueOracle


def test_no_false_negative_on_small_exhaustive_domains():
    for c_max in [1, 5, 31]:
        for r in range(1, 6):
            for A in range(A_min_for_period(r), 13):
                D = (1 << A) - 3**r
                eligible = eligible_divisors(D, c_max)
                for valuations in compositions(A, r):
                    C = cycle_constant(valuations)
                    c = D // gcd(D, C)
                    if c > c_max:
                        continue

                    oracle = ReachableResidueOracle()
                    S = 0
                    P = 0
                    for t in range(r):
                        assert prefix_can_reach_threshold(
                            r=r,
                            A=A,
                            D=D,
                            c_max=c_max,
                            t=t,
                            S=S,
                            P=P,
                            eligible=eligible,
                            oracle=oracle,
                        )
                        P = prefix_constant_after_append(r, t, S, P)
                        S += valuations[t]
