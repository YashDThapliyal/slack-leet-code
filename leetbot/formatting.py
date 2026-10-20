"""The text of every message the bot posts, in one place so wording is easy to change."""

from datetime import date

from leetbot.dates import format_range
from leetbot.leetcode import DailyProblem
from leetbot.stats import Ranked

MEDALS = {1: "🥇", 2: "🥈", 3: "🥉"}

HELP = (
    "*How to use the bot*\n"
    "• Log a solve: reply in today's daily thread with `leet <problem> <difficulty>` and a screenshot "
    "of your accepted solution, e.g. `leet Two Sum easy`. Easy = 1 pt, Medium = 2, Hard = 3.\n"
    "• `leet board`: this week's leaderboard. `leet board all`: all-time.\n"
    "• `leet me`: your points, solves and streaks.\n"
    "• Admins: `leet add @person <points> <reason>` / `leet remove @person <points> <reason>`."
)
NEED_THREAD = "🧵 Log solves as a reply in today's daily thread (the bot's morning post)."
NEED_SCREENSHOT = "📸 No screenshot, no points! Post it again with a screenshot of your accepted solution attached."
NEED_PROBLEM = "Which problem? Try something like `leet Two Sum easy` (with your screenshot)."
MISSING_DIFFICULTY = "Counted as Easy (1 pt). Next time add the difficulty, e.g. `leet Two Sum medium`."
ADMIN_ONLY = "Only admins can add or remove points."
ERROR = "😵 Something went wrong on my end. Try again in a minute, or ping an admin."


def morning(daily: DailyProblem | None) -> str:
    lines = ["<!channel> ☀️ Time to solve a problem today!"]
    if daily:
        lines.append(f"Today's LeetCode daily: *<{daily.url}|{daily.title}>* ({daily.difficulty})")
    lines.append("…or solve any problem! Any problem from any site counts.")
    lines.append("Log it in this thread: `leet <problem> <difficulty>` + a screenshot of your accepted solution.")
    return "\n".join(lines)


def evening(missing_names: list[str]) -> str:
    if not missing_names:
        return "🎉 Everyone solved a problem today! Amazing work, keep the streaks going 🔥"
    return f"These people didn't solve a problem today: {', '.join(missing_names)}… booo 👎"


def board(ranked: list[Ranked], streaks: dict[str, int], title: str) -> str:
    if not ranked:
        return f"*{title}*\nNo points yet. Be the first! 🚀"
    lines = [f"*{title}*"]
    for row in ranked:
        streak = streaks.get(row.total.user_id, 0)
        lines.append(f"{row.rank}. {row.total.name}: {row.total.points} pts · 🔥 {streak}")
    return "\n".join(lines)


def week_title(prefix: str, start: date, end: date) -> str:
    return f"{prefix} ({format_range(start, end)})"


def me(week_points: int, all_points: int, counts: dict[str, int], current: int, best: int) -> str:
    easy, medium, hard = counts.get("easy", 0), counts.get("medium", 0), counts.get("hard", 0)
    return (
        "*Your stats*\n"
        f"This week: {week_points} pts · All-time: {all_points} pts\n"
        f"Problems solved: {easy + medium + hard} ({easy} easy · {medium} medium · {hard} hard)\n"
        f"Current streak: {_days(current)} · Best streak: {_days(best)}"
    )


def weekly(top: list[Ranked], streak_names: list[str], streak: int, start: date, end: date) -> str:
    header = f"🏆 *Weekly recap* ({format_range(start, end)})"
    if not top:
        return f"{header}\nNo solves logged this week. New week starts tomorrow 💪"
    lines = [header]
    for row in top:
        lines.append(f"{MEDALS.get(row.rank, f'{row.rank}.')} {row.total.name}: {row.total.points} pts")
    if streak > 0:
        lines.append(f"🔥 Longest active streak: {', '.join(streak_names)} with {_days(streak)}")
    return "\n".join(lines)


def adjusted(sign: int, points: int, name: str, reason: str) -> str:
    verb = f"Added {points} pts to" if sign > 0 else f"Removed {points} pts from"
    return f"✅ {verb} {name}. Reason: {reason}"


def _days(n: int) -> str:
    return f"{n} day" if n == 1 else f"{n} days"
