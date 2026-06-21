import pytest

from src.reachable_residues import (
    ReachableResidueOracle,
    brute_force_reachable_residues,
    reachable_residues,
)


@pytest.mark.parametrize("g", [1, 5, 7, 31])
def test_base_case(g):
    assert reachable_residues(1, 4, g) == frozenset({1 % g})


@pytest.mark.parametrize("m", range(1, 5))
@pytest.mark.parametrize("B", range(1, 9))
@pytest.mark.parametrize("g", [1, 5, 7, 9, 31])
def test_dp_matches_bruteforce_for_small_states(m, B, g):
    if B < m:
        return
    assert reachable_residues(m, B, g) == brute_force_reachable_residues(m, B, g)


def test_oracle_memoizes_states_and_tracks_max_size():
    oracle = ReachableResidueOracle()
    first = oracle.reachable(4, 8, 31)
    entries_after_first = oracle.cache_entries
    second = oracle.reachable(4, 8, 31)
    assert first == second
    assert oracle.cache_entries == entries_after_first
    assert oracle.max_set_size >= len(first)


def test_reachable_residues_rejects_invalid_states():
    with pytest.raises(ValueError):
        reachable_residues(0, 0, 1)
    with pytest.raises(ValueError):
        reachable_residues(2, 1, 1)
    with pytest.raises(ValueError):
        reachable_residues(1, 1, 2)
