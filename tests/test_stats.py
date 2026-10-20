from datetime import date, timedelta

from leetbot.dates import pacific_date, week_bounds
from leetbot.stats import Total, best_streak, current_streak, rank

TODAY = date(2026, 10, 21)  # a Wednesday


def days_ago(*offsets: int) -> set[date]:
    return {TODAY - timedelta(days=n) for n in offsets}


def test_current_streak_includes_today():
    assert current_streak(days_ago(0, 1, 2), TODAY) == 3


def test_streak_survives_until_the_day_ends():
    assert current_streak(days_ago(1, 2), TODAY) == 2


def test_streak_breaks_after_a_missed_day():
    assert current_streak(days_ago(2, 3), TODAY) == 0
    assert current_streak(set(), TODAY) == 0


def test_best_streak():
    assert best_streak(days_ago(0, 3, 4, 5, 8)) == 3
    assert best_streak(set()) == 0


def test_week_runs_monday_to_sunday():
    assert week_bounds(TODAY) == (date(2026, 10, 19), date(2026, 10, 25))
    assert week_bounds(date(2026, 10, 25)) == (date(2026, 10, 19), date(2026, 10, 25))
    assert week_bounds(date(2026, 10, 26))[0] == date(2026, 10, 26)


def test_pacific_date_uses_pacific_midnight():
    # 06:30 UTC on Oct 21 is 11:30pm Oct 20 in Pacific (daylight time)
    assert pacific_date("1792564200.000000") == date(2026, 10, 20)


def test_rank_shares_ties():
    ranked = rank([Total("a", "Ann", 5), Total("b", "bob", 7), Total("c", "Cy", 5), Total("d", "Di", 1)])
    assert [(r.rank, r.total.name) for r in ranked] == [(1, "bob"), (2, "Ann"), (2, "Cy"), (4, "Di")]
