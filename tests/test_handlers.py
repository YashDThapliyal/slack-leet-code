from datetime import timedelta
from itertools import count

import pytest

from leetbot import formatting
from leetbot.dates import pacific_today
from leetbot.handlers import handle_message
from leetbot.posts import post_morning
from tests.conftest import ADMIN, CHANNEL, slack_ts

TODAY = pacific_today()
IMAGE = [{"mimetype": "image/png"}]
_minutes = count(1)


@pytest.fixture
def thread(client, config, store) -> str:
    """Today's morning post, which is the thread solves are logged in."""
    post_morning(client, config, store, TODAY, fetch_daily=lambda: None)
    client.posts.clear()
    return store_thread(store, TODAY)


def store_thread(store, day) -> str:
    with store._connect() as conn:
        return conn.execute(
            "SELECT slack_ts FROM daily_posts WHERE kind = 'morning' AND post_date = %s", (day,)
        ).fetchone()[0]


def send(client, config, store, text, user="U0ALICE", thread_ts=None, files=IMAGE, ts=None, event_id=None, **extra):
    ts = ts or slack_ts(TODAY, 10, next(_minutes) % 60)
    event = {"type": "message", "channel": CHANNEL, "user": user, "text": text, "ts": ts, "files": files, **extra}
    if thread_ts:
        event["thread_ts"] = thread_ts
    handle_message(event, event_id or f"Ev{ts}", client, config, store)
    return ts


def reactions(client):
    return [r["name"] for r in client.reactions]


def test_solve_in_daily_thread_scores_points(client, config, store, thread):
    send(client, config, store, "leet Two Sum medium", thread_ts=thread)
    assert reactions(client) == ["white_check_mark"]
    assert client.posts == []
    assert store.totals()[0].points == 2
    assert store.totals()[0].name == "alice"


def test_missing_difficulty_counts_easy_and_reminds(client, config, store, thread):
    send(client, config, store, "leet Two Sum", thread_ts=thread)
    assert reactions(client) == ["white_check_mark"]
    assert client.texts() == [formatting.MISSING_DIFFICULTY]
    assert store.totals()[0].points == 1


def test_multiple_solves_and_duplicates(client, config, store, thread):
    send(client, config, store, "leet Two Sum e", thread_ts=thread)
    send(client, config, store, "leet Valid Anagram e", thread_ts=thread)
    send(client, config, store, "leet 1. two-sum easy", thread_ts=thread)
    assert reactions(client) == ["white_check_mark", "white_check_mark", "repeat"]
    assert store.totals()[0].points == 2


def test_different_people_can_solve_the_same_problem(client, config, store, thread):
    send(client, config, store, "leet Two Sum e", user="U0ALICE", thread_ts=thread)
    send(client, config, store, "leet Two Sum e", user="U0BOB", thread_ts=thread)
    assert reactions(client) == ["white_check_mark", "white_check_mark"]


def test_no_screenshot_no_points(client, config, store, thread):
    send(client, config, store, "leet Two Sum easy", thread_ts=thread, files=[])
    send(client, config, store, "leet Two Sum easy", thread_ts=thread, files=[{"mimetype": "application/pdf"}])
    assert client.texts() == [formatting.NEED_SCREENSHOT] * 2
    assert store.totals() == []


def test_solve_outside_daily_thread_rejected(client, config, store, thread):
    send(client, config, store, "leet Two Sum easy")
    send(client, config, store, "leet Two Sum easy", thread_ts="1.000001")
    assert client.texts() == [formatting.NEED_THREAD] * 2
    assert store.totals() == []


def test_before_morning_ping_yesterdays_thread_counts_for_today(client, config, store):
    yesterday = TODAY - timedelta(days=1)
    post_morning(client, config, store, yesterday, fetch_daily=lambda: None)
    old_thread = store_thread(store, yesterday)
    send(client, config, store, "leet Two Sum easy", thread_ts=old_thread, ts=slack_ts(TODAY, 1))
    assert reactions(client) == ["white_check_mark"]
    assert store.solve_days()["U0ALICE"] == {TODAY}


def test_threads_older_than_yesterday_rejected(client, config, store):
    old_day = TODAY - timedelta(days=2)
    post_morning(client, config, store, old_day, fetch_daily=lambda: None)
    client.posts.clear()
    send(client, config, store, "leet Two Sum easy", thread_ts=store_thread(store, old_day))
    assert client.texts() == [formatting.NEED_THREAD]


def test_slack_retry_is_ignored(client, config, store, thread):
    ts = send(client, config, store, "leet Two Sum easy", thread_ts=thread, event_id="Ev1")
    send(client, config, store, "leet Two Sum easy", thread_ts=thread, ts=ts, event_id="Ev1")
    assert reactions(client) == ["white_check_mark"]


def test_ignores_other_channels_bots_and_edits(client, config, store, thread):
    handle_message({"channel": "C_OTHER", "user": "U0ALICE", "text": "leet board", "ts": "1.1"}, "E1", client, config, store)
    send(client, config, store, "leet board", files=[], bot_id="B1")
    send(client, config, store, "leet board", files=[], subtype="message_changed")
    send(client, config, store, "hello everyone", files=[])
    assert client.posts == [] and client.reactions == []


def test_leet_board_week_and_all_time(client, config, store, thread):
    send(client, config, store, "leet Two Sum hard", user="U0BOB", thread_ts=thread)
    send(client, config, store, "leet Valid Anagram e", user="U0ALICE", thread_ts=thread)
    send(client, config, store, "leet board", files=[])
    send(client, config, store, "leet board all-time", files=[])
    week, all_time = client.texts()
    assert week.startswith("*This week's leaderboard")
    assert "1. bob: 3 pts · 🔥 1\n2. alice: 1 pts · 🔥 1" in week
    assert all_time.startswith("*All-time leaderboard*")


def test_commands_reply_in_thread(client, config, store, thread):
    ts = send(client, config, store, "leet help", files=[])
    assert client.posts[0]["thread_ts"] == ts


def test_leet_me(client, config, store, thread):
    send(client, config, store, "leet Two Sum m", thread_ts=thread)
    send(client, config, store, "leet Valid Anagram h", thread_ts=thread)
    send(client, config, store, "leet me", files=[])
    text = client.texts()[-1]
    assert "This week: 5 pts · All-time: 5 pts" in text
    assert "Problems solved: 2 (0 easy · 1 medium · 1 hard)" in text
    assert "Current streak: 1 day · Best streak: 1 day" in text


def test_admin_can_add_and_remove_points(client, config, store, thread):
    send(client, config, store, "leet Two Sum h", thread_ts=thread)
    send(client, config, store, "leet remove <@U0ALICE> 3 fake screenshot", user=ADMIN, files=[])
    send(client, config, store, "leet add <@U0ALICE> 1 forgot to log", user=ADMIN, files=[])
    assert client.texts() == [
        "✅ Removed 3 pts from alice. Reason: fake screenshot",
        "✅ Added 1 pts to alice. Reason: forgot to log",
    ]
    assert store.totals()[0].points == 1


def test_non_admin_cannot_adjust(client, config, store, thread):
    send(client, config, store, "leet add <@U0ALICE> 5 trust me", user="U0ALICE", files=[])
    send(client, config, store, "leet add <@U0ALICE>", user="U0ALICE", files=[])
    assert client.texts() == [formatting.ADMIN_ONLY] * 2
    assert store.totals() == []


def test_unexpected_error_gets_friendly_reply(client, config, store, thread, monkeypatch):
    monkeypatch.setattr(store, "totals", lambda *a: 1 / 0)
    send(client, config, store, "leet board", files=[])
    assert client.texts() == [formatting.ERROR]
