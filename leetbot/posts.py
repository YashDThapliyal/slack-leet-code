"""The scheduled posts, triggered by cron. Each posts at most once per day even if cron retries."""

import logging
from collections.abc import Callable
from datetime import date

from slack_sdk import WebClient

from leetbot import formatting
from leetbot.config import Config
from leetbot.dates import week_bounds
from leetbot.leetcode import DailyProblem, fetch_daily_problem
from leetbot.stats import current_streak, rank
from leetbot.store import Store

logger = logging.getLogger(__name__)

TOP_RANKS = 3


def post_morning(
    client: WebClient,
    config: Config,
    store: Store,
    today: date,
    fetch_daily: Callable[[], DailyProblem | None] = fetch_daily_problem,
) -> str:
    try:
        store.prune_events()
    except Exception:
        logger.warning("Couldn't prune old Slack event IDs; will try again tomorrow", exc_info=True)
    return _post_once("morning", client, config, store, today, lambda: formatting.morning(fetch_daily()))


def post_evening(client: WebClient, config: Config, store: Store, today: date) -> str:
    statuses = store.day_status(today)
    if not statuses:
        return "skipped: nobody has logged a solve yet"
    missing = sorted((s.name for s in statuses if not s.solved), key=str.lower)
    return _post_once("evening", client, config, store, today, lambda: formatting.evening(missing))


def post_weekly(client: WebClient, config: Config, store: Store, today: date) -> str:
    start, end = week_bounds(today)
    top = [row for row in rank(store.totals(start, end)) if row.rank <= TOP_RANKS and row.total.points > 0]
    names = {t.user_id: t.name for t in store.totals()}
    streaks = {user_id: current_streak(days, today) for user_id, days in store.solve_days().items()}
    longest = max(streaks.values(), default=0)
    streak_names = sorted((names[u] for u, s in streaks.items() if s == longest and longest > 0), key=str.lower)
    text = formatting.weekly(top, streak_names, longest, start, end)
    return _post_once("weekly", client, config, store, today, lambda: text)


JOBS: dict[str, Callable[[WebClient, Config, Store, date], str]] = {"morning": post_morning, "evening": post_evening, "weekly": post_weekly}


def _post_once(kind: str, client: WebClient, config: Config, store: Store, today: date, build_text) -> str:
    if not store.claim_post(kind, today):
        return "skipped: already posted today"
    try:
        response = client.chat_postMessage(channel=config.channel_id, text=build_text())
    except Exception:
        store.release_post(kind, today)
        raise
    store.set_post_ts(kind, today, response["ts"])
    logger.info("Posted %s message for %s", kind, today)
    return "posted"
