from math import gcd

from src.core import (
    A_max_general,
    A_min_for_period,
    candidate_start,
    canonical_cycle_and_valuations,
    cycle_constant,
    is_normalized_parameter,
    odd_map,
    verify_candidate,
)


def test_known_fixed_points():
    # 3*1+1=4 and 3*1+5=8.
    assert odd_map(1, 1) == 1
    assert odd_map(1, 5) == 1
    assert verify_candidate(1, (2,), 1) is not None
    fixed_5 = verify_candidate(5, (3,), 1)
    assert fixed_5 is not None
    assert fixed_5.essential


def test_scaling_inheritance():
    # Scaling the c=5, n=1 fixed point by odd d=3 gives c=15, n=3.
    inherited = verify_candidate(15, (3,), 3)
    assert inherited is not None
    assert inherited.shared_gcd == 3
    assert not inherited.essential


def test_cycle_identity_for_known_fixed_point():
    vals = (3,)
    D = (1 << sum(vals)) - 3
    assert D == 5
    assert cycle_constant(vals) == 1
    assert candidate_start(5, vals) == 1


def test_shared_rotation_alignment():
    orbit = (7, 5, 1)
    vals = (1, 2, 3)
    co, cv, offset = canonical_cycle_and_valuations(orbit, vals)
    assert co == (1, 7, 5)
    assert cv == (3, 1, 2)
    assert offset == 2


def test_exact_A_bounds():
    assert A_min_for_period(1) == 2
    assert A_max_general(1, 4) == 8
    assert A_max_general(5, 1) == 3


def test_normalized_parameter_filter():
    assert is_normalized_parameter(1)
    assert is_normalized_parameter(5)
    assert not is_normalized_parameter(3)
    assert not is_normalized_parameter(9)
    assert not is_normalized_parameter(2)
