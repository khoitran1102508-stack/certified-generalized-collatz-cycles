import pytest

from src.divisors import divisors, eligible_divisors, factorize


def test_factorize_small_values():
    assert factorize(1) == {}
    assert factorize(2) == {2: 1}
    assert factorize(45) == {3: 2, 5: 1}
    assert factorize(2**5 * 7**2) == {2: 5, 7: 2}


def test_divisors_are_sorted_and_complete():
    assert divisors(1) == (1,)
    assert divisors(12) == (1, 2, 3, 4, 6, 12)
    assert divisors(45) == (1, 3, 5, 9, 15, 45)


def test_eligible_divisors():
    # D/g <= 5 means g >= 9 among divisors of 45.
    assert eligible_divisors(45, 5) == (9, 15, 45)
    assert eligible_divisors(45, 1) == (45,)
    assert eligible_divisors(45, 100) == divisors(45)


@pytest.mark.parametrize("bad", [0, -1])
def test_factorize_rejects_nonpositive(bad):
    with pytest.raises(ValueError):
        factorize(bad)


def test_eligible_divisors_rejects_bad_inputs():
    with pytest.raises(ValueError):
        eligible_divisors(0, 5)
    with pytest.raises(ValueError):
        eligible_divisors(45, 0)
