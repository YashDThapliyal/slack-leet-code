"""Every "day" and "week" in the bot is a Pacific-time day or week."""

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

PACIFIC = ZoneInfo("America/Los_Angeles")


def pacific_today() -> date:
    return datetime.now(PACIFIC).date()


def pacific_date(slack_ts: str) -> date:
    """Pacific date of a Slack message timestamp like "1729370000.000100"."""
    return datetime.fromtimestamp(float(slack_ts), tz=PACIFIC).date()


def week_bounds(day: date) -> tuple[date, date]:
    """Monday and Sunday of the week containing `day`."""
    monday = day - timedelta(days=day.weekday())
    return monday, monday + timedelta(days=6)


def format_range(start: date, end: date) -> str:
    return f"{start:%b} {start.day} – {end:%b} {end.day}"
