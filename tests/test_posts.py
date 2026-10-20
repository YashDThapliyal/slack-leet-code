from datetime import date, timedelta
from itertools import count

import pytest

from leetbot.leetcode import DailyProblem
from leetbot.posts import post_evening, post_morning, post_weekly
from leetbot.store import SolveRecord
from tests.conftest import CHANNEL, slack_ts

SUNDAY = date(2026, 10, 25)
_minutes = count(1)
DAILY = DailyProblem("Two Sum", "Easy", "https://leetcode.com/problems/two-sum/")


def solve(store, user, name, day, problem, points=1):
    store.add_solve(
        SolveRecord(user, name, problem, problem.lower(), {1: "easy", 2: "medium", 3: "hard"}[points], points, day,
                    slack_ts(day, 12, next(_minutes) % 60))
    )


def test_morning_post_includes_daily(client, config, store):
    assert post_morning(client, config, store, SUNDAY, fetch_daily=lambda: DAILY) == "posted"
    text = client.posts[0]["text"]
    assert client.posts[0]["channel"] == CHANNEL
    assert text.startswith("<!channel>")
    assert "*<https://leetcode.com/problems/two-sum/|Two Sum>* (Easy)" in text
    assert "or solve any problem!" in text


def test_morning_post_without_daily(client, config, store):
    post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None)
    assert "LeetCode daily" not in client.posts[0]["text"]
    assert "or solve any problem!" in client.posts[0]["text"]


def test_cron_retry_does_not_double_post(client, config, store):
    post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None)
    assert post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None) == "skipped: already posted today"
    assert len(client.posts) == 1


def test_failed_post_can_be_retried(client, config, store, monkeypatch):
    def fail(**kwargs):
        raise RuntimeError("slack down")

    monkeypatch.setattr(client, "chat_postMessage", fail)
    with pytest.raises(RuntimeError):
        post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None)
    monkeypatch.undo()
    assert post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None) == "posted"


def test_stuck_claim_is_reclaimed_by_backup_run(client, config, store):
    # Process died after claiming but before Slack returned a ts
    store.claim_post("morning", SUNDAY)
    assert post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None).startswith("skipped")
    with store._connect() as conn:
        conn.execute("UPDATE daily_posts SET created_at = now() - interval '5 minutes'")
    assert post_morning(client, config, store, SUNDAY, fetch_daily=lambda: None) == "posted"


def test_evening_boo_list_skips_lurkers_and_uses_plain_names(client, config, store):
    solve(store, "U0ALICE", "alice", SUNDAY, "a")
    solve(store, "U0BOB", "bob", SUNDAY - timedelta(days=3), "b")
    solve(store, "U0CARA", "Cara", SUNDAY - timedelta(days=1), "c")
    post_evening(client, config, store, SUNDAY)
    assert client.posts[0]["text"] == "These people didn't solve a problem today: bob, Cara… booo 👎"


def test_evening_celebrates_when_everyone_solved(client, config, store):
    solve(store, "U0ALICE", "alice", SUNDAY, "a")
    post_evening(client, config, store, SUNDAY)
    assert client.posts[0]["text"].startswith("🎉 Everyone solved")


def test_evening_skipped_before_anyone_has_solved(client, config, store):
    assert post_evening(client, config, store, SUNDAY).startswith("skipped")
    assert client.posts == []


def test_weekly_recap_top_three_and_streak(client, config, store):
    monday = SUNDAY - timedelta(days=6)
    solve(store, "U0ALICE", "alice", monday - timedelta(days=1), "last week", points=3)  # not this week
    for i in range(7):
        solve(store, "U0ALICE", "alice", monday + timedelta(days=i), f"a{i}")
    solve(store, "U0BOB", "bob", SUNDAY, "b1", points=3)
    solve(store, "U0BOB", "bob", SUNDAY, "b2", points=3)
    solve(store, "U0CARA", "cara", SUNDAY, "c1", points=2)
    solve(store, "U0DAN", "dan", SUNDAY, "d1", points=1)
    store.add_adjustment("U0DAN", "dan", 1, "bonus", "U0ADMIN", SUNDAY)

    post_weekly(client, config, store, SUNDAY)
    assert client.posts[0]["text"] == (
        "🏆 *Weekly recap* (Oct 19 – Oct 25)\n"
        "🥇 alice: 7 pts\n"
        "🥈 bob: 6 pts\n"
        "🥉 cara: 2 pts\n"
        "🥉 dan: 2 pts\n"
        "🔥 Longest active streak: alice with 8 days"
    )


def test_weekly_recap_leaves_out_people_without_positive_points(client, config, store):
    solve(store, "U0ALICE", "alice", SUNDAY, "a")
    store.add_adjustment("U0BOB", "bob", -2, "fake", "U0ADMIN", SUNDAY)
    post_weekly(client, config, store, SUNDAY)
    assert "bob" not in client.posts[0]["text"]


def test_failed_name_lookup_does_not_replace_real_name(client, config, store):
    solve(store, "U0ALICE", "alice", SUNDAY, "a")
    solve(store, "U0ALICE", "U0ALICE", SUNDAY, "b")  # Slack lookup failed on the later solve
    assert store.totals()[0].name == "alice"


def test_weekly_recap_with_no_solves(client, config, store):
    post_weekly(client, config, store, SUNDAY)
    assert "No solves logged this week" in client.posts[0]["text"]
