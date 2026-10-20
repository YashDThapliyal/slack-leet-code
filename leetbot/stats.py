"""Streak and ranking math. Pure functions, no Slack or database."""

from dataclasses import dataclass
from datetime import date, timedelta

ONE_DAY = timedelta(days=1)


@dataclass(frozen=True)
class Total:
    user_id: str
    name: str
    points: int


@dataclass(frozen=True)
class Ranked:
    rank: int
    total: Total


def current_streak(days: set[date], today: date) -> int:
    """Consecutive solve days ending today, or ending yesterday if today has no solve yet.

    A streak only breaks once a whole day passes with no solve.
    """
    day = today if today in days else today - ONE_DAY
    streak = 0
    while day in days:
        streak += 1
        day -= ONE_DAY
    return streak


def best_streak(days: set[date]) -> int:
    best = 0
    for day in days:
        if day - ONE_DAY in days:
            continue  # not the start of a run
        length = 1
        while day + timedelta(days=length) in days:
            length += 1
        best = max(best, length)
    return best


def rank(totals: list[Total]) -> list[Ranked]:
    """Highest points first. Ties share a rank (1, 2, 2, 4) and are ordered by name."""
    ordered = sorted(totals, key=lambda t: (-t.points, t.name.lower()))
    ranked: list[Ranked] = []
    for i, total in enumerate(ordered):
        tied = i > 0 and total.points == ordered[i - 1].points
        ranked.append(Ranked(rank=ranked[-1].rank if tied else i + 1, total=total))
    return ranked
