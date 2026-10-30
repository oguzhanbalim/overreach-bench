from __future__ import annotations

import pytest

from overreach_bench.stats import Rate, sign_test, wilson


@pytest.mark.parametrize(
    ("k", "n", "low", "high"),
    [
        # Worked by hand from the formula, and the 8/10 row matches published Wilson tables.
        (0, 10, 0.0, 0.2775),
        (10, 10, 0.7225, 1.0),
        (5, 10, 0.2366, 0.7634),
        (8, 10, 0.4902, 0.9433),
        (1, 2, 0.0945, 0.9055),
        (0, 36, 0.0, 0.0964),
        (36, 36, 0.9036, 1.0),
    ],
)
def test_wilson_known_values(k, n, low, high):
    got_low, got_high = wilson(k, n)
    assert got_low == pytest.approx(low, abs=1e-4)
    assert got_high == pytest.approx(high, abs=1e-4)


def test_wilson_rejects_impossible_input():
    with pytest.raises(ValueError):
        wilson(0, 0)
    with pytest.raises(ValueError):
        wilson(3, 2)


@pytest.mark.parametrize(
    ("plus", "minus", "p"),
    [
        (0, 0, 1.0),
        (1, 0, 1.0),
        (5, 5, 1.0),
        (2, 0, 0.5),
        (6, 0, 0.03125),
        (10, 0, 2 / 1024),
        (8, 2, 0.109375),
        (0, 10, 2 / 1024),
        (36, 0, 2 / 2**36),
    ],
)
def test_sign_test_known_values(plus, minus, p):
    assert sign_test(plus, minus) == pytest.approx(p)


def test_sign_test_is_symmetric():
    assert sign_test(7, 3) == sign_test(3, 7)


def test_rate_with_nothing_measured_says_so_and_overlaps_everything():
    empty = Rate(0, 0)
    assert empty.value is None
    assert empty.text() == "n/a"
    assert empty.overlaps(Rate(10, 10))


def test_rate_overlap():
    assert Rate(5, 10).overlaps(Rate(6, 10))
    assert not Rate(0, 36).overlaps(Rate(36, 36))
