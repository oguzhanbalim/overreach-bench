"""Wilson intervals and the exact sign test. Standard library only."""

from __future__ import annotations

from dataclasses import dataclass
from math import comb, sqrt

Z_95 = 1.959963984540054


def wilson(successes: int, n: int, z: float = Z_95) -> tuple[float, float]:
    """The Wilson score interval for a proportion. Well behaved at 0/n and n/n."""
    if n <= 0:
        raise ValueError("a Wilson interval needs at least one observation")
    if not 0 <= successes <= n:
        raise ValueError(f"successes must be between 0 and {n}")
    p = successes / n
    z2 = z * z
    denominator = 1 + z2 / n
    centre = (p + z2 / (2 * n)) / denominator
    half = z * sqrt(p * (1 - p) / n + z2 / (4 * n * n)) / denominator
    # At the edges the true bound is exactly 0 or 1. Floating point should not blur it.
    low = 0.0 if successes == 0 else max(0.0, centre - half)
    high = 1.0 if successes == n else min(1.0, centre + half)
    return low, high


def sign_test(plus: int, minus: int) -> float:
    """Two-sided exact sign test over discordant pairs. Same as exact McNemar.

    With no discordant pairs there is no evidence of any difference, so the p-value is 1.
    """
    if plus < 0 or minus < 0:
        raise ValueError("counts cannot be negative")
    n = plus + minus
    if n == 0:
        return 1.0
    tail = sum(comb(n, k) for k in range(min(plus, minus) + 1))
    return min(1.0, 2 * tail / 2**n)


@dataclass(frozen=True)
class Rate:
    """A count with its Wilson interval. ``n`` is zero when nothing could be measured."""

    k: int
    n: int

    @property
    def value(self) -> float | None:
        return self.k / self.n if self.n else None

    @property
    def interval(self) -> tuple[float, float] | None:
        return wilson(self.k, self.n) if self.n else None

    def overlaps(self, other: Rate) -> bool:
        """No interval means no information, which is treated as overlapping everything."""
        one, two = self.interval, other.interval
        if one is None or two is None:
            return True
        return one[0] <= two[1] and two[0] <= one[1]

    def text(self) -> str:
        if self.interval is None:
            return "n/a"
        low, high = self.interval
        return f"{self.value:.0%} [{low:.0%}, {high:.0%}]"

    def to_dict(self) -> dict[str, object]:
        interval = self.interval
        return {
            "k": self.k,
            "n": self.n,
            "rate": round(self.value, 4) if self.n else None,
            "ci95": [round(interval[0], 4), round(interval[1], 4)] if interval else None,
        }
