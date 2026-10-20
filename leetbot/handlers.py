"""Handle messages in the leet channel: log solves, answer commands, apply admin adjustments."""

import logging

from slack_sdk import WebClient

from leetbot import formatting
from leetbot.config import Config
from leetbot.dates import pacific_date, pacific_today, week_bounds
from leetbot.parsing import Adjust, AdjustUsageError, Command, Solve, parse
from leetbot.stats import ONE_DAY, best_streak, current_streak, rank
from leetbot.store import SolveRecord, Store

logger = logging.getLogger(__name__)

# Plain messages, messages with uploads, and "also send to channel" thread replies
HANDLED_SUBTYPES = (None, "file_share", "thread_broadcast")
OK_REACTION = "white_check_mark"
DUPLICATE_REACTION = "repeat"


def handle_message(event: dict, event_id: str, client: WebClient, config: Config, store: Store) -> None:
    if event.get("channel") != config.channel_id:
        return
    if event.get("bot_id") or event.get("subtype") not in HANDLED_SUBTYPES or not event.get("user"):
        return
    has_image = any((f.get("mimetype") or "").startswith("image/") for f in event.get("files") or [])
    parsed = parse(event.get("text") or "", has_image)
    if parsed is None:
        return
    if not store.claim_event(event_id or event["ts"]):
        logger.info("Skipping Slack retry of event %s", event_id)
        return

    reply = _replier(client, event)
    try:
        if isinstance(parsed, Solve):
            _log_solve(parsed, has_image, event, client, store, reply)
        elif isinstance(parsed, Command):
            _run_command(parsed, event["user"], store, reply)
        elif isinstance(parsed, AdjustUsageError):
            reply(parsed.message if event["user"] in config.admin_ids else formatting.ADMIN_ONLY)
        elif isinstance(parsed, Adjust):
            _adjust(parsed, event["user"], client, config, store, reply)
    except Exception:
        logger.exception("Failed to handle message %s", event.get("ts"))
        reply(formatting.ERROR)


def _replier(client: WebClient, event: dict):
    thread_ts = event.get("thread_ts") or event["ts"]

    def reply(text: str) -> None:
        try:
            client.chat_postMessage(channel=event["channel"], thread_ts=thread_ts, text=text)
        except Exception:
            logger.exception("Couldn't reply in thread %s", thread_ts)

    return reply


def _log_solve(solve: Solve, has_image: bool, event: dict, client: WebClient, store: Store, reply) -> None:
    solve_date = pacific_date(event["ts"])
    # Today's thread, or yesterday's for solves posted before the 9am ping
    threads = [solve_date, solve_date - ONE_DAY]
    if not event.get("thread_ts") or not store.is_daily_thread(event["thread_ts"], threads):
        reply(formatting.NEED_THREAD)
        return
    if not has_image:
        reply(formatting.NEED_SCREENSHOT)
        return
    if not solve.problem_key:
        reply(formatting.NEED_PROBLEM)
        return

    record = SolveRecord(
        user_id=event["user"],
        user_name=display_name(client, event["user"]),
        problem=solve.problem,
        problem_key=solve.problem_key,
        difficulty=solve.difficulty,
        points=solve.points,
        solve_date=solve_date,
        slack_ts=event["ts"],
    )
    if not store.add_solve(record):
        _react(client, event, DUPLICATE_REACTION)
        return
    _react(client, event, OK_REACTION)
    if not solve.difficulty_given:
        reply(formatting.MISSING_DIFFICULTY)


def _run_command(command: Command, user_id: str, store: Store, reply) -> None:
    today = pacific_today()
    if command.name == "help":
        reply(formatting.HELP)
    elif command.name == "board":
        all_time = any(arg.startswith("all") for arg in command.args)  # all, all-time, alltime
        reply(_board_text(store, all_time=all_time, today=today))
    elif command.name == "me":
        reply(_me_text(store, user_id, today))


def _board_text(store: Store, all_time: bool, today) -> str:
    days = store.solve_days()
    streaks = {user_id: current_streak(d, today) for user_id, d in days.items()}
    if all_time:
        return formatting.board(rank(store.totals()), streaks, "All-time leaderboard")
    start, end = week_bounds(today)
    title = formatting.week_title("This week's leaderboard", start, end)
    return formatting.board(rank(store.totals(start, end)), streaks, title)


def _me_text(store: Store, user_id: str, today) -> str:
    start, end = week_bounds(today)
    week = {t.user_id: t.points for t in store.totals(start, end)}
    all_time = {t.user_id: t.points for t in store.totals()}
    days = store.solve_days().get(user_id, set())
    return formatting.me(
        week_points=week.get(user_id, 0),
        all_points=all_time.get(user_id, 0),
        counts=store.difficulty_counts(user_id),
        current=current_streak(days, today),
        best=best_streak(days),
    )


def _adjust(adjust: Adjust, admin_id: str, client: WebClient, config: Config, store: Store, reply) -> None:
    if admin_id not in config.admin_ids:
        reply(formatting.ADMIN_ONLY)
        return
    name = display_name(client, adjust.user_id)
    store.add_adjustment(
        user_id=adjust.user_id,
        user_name=name,
        points=adjust.sign * adjust.points,
        reason=adjust.reason,
        admin_id=admin_id,
        adjust_date=pacific_today(),
    )
    reply(formatting.adjusted(adjust.sign, adjust.points, name, adjust.reason))


def display_name(client: WebClient, user_id: str) -> str:
    """Slack display name, falling back to real name, then the raw ID if Slack can't be reached."""
    try:
        user = client.users_info(user=user_id)["user"]
        profile = user.get("profile") or {}
        return profile.get("display_name") or profile.get("real_name") or user.get("real_name") or user.get("name") or user_id
    except Exception:
        logger.warning("Couldn't look up Slack name for %s", user_id, exc_info=True)
        return user_id


def _react(client: WebClient, event: dict, emoji: str) -> None:
    try:
        client.reactions_add(channel=event["channel"], timestamp=event["ts"], name=emoji)
    except Exception:
        logger.exception("Couldn't add :%s: to %s", emoji, event["ts"])
