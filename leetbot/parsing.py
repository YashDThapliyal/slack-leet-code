"""Turn a raw Slack message into a command, an admin adjustment, or a logged solve."""

import html
import re
from dataclasses import dataclass

DIFFICULTY_POINTS = {"easy": 1, "medium": 2, "hard": 3}
DEFAULT_DIFFICULTY = "easy"
_DIFFICULTY_ALIASES = {
    "easy": ("easy", "e", "ez", "eazy", "esay", "eas"),
    "medium": ("medium", "med", "m", "mid", "meduim", "medum", "mediun"),
    "hard": ("hard", "h", "hrd", "hrad", "har"),
}
_ALIAS_TO_DIFFICULTY = {alias: name for name, aliases in _DIFFICULTY_ALIASES.items() for alias in aliases}

# Command words after "leet". Words of 4+ letters also match with one typo ("bord", "borad").
_COMMAND_ALIASES = {
    "board": ("board", "leaderboard", "lb"),
    "me": ("me", "stats"),
    "help": ("help",),
}
_FUZZY_MIN_LENGTH = 4
# Common slips of the prefix. Deliberately a fixed list: fuzzy-matching "leet" would also catch
# everyday words like "let", "left" and "meet".
_PREFIXES = ("leet", "leeet", "leett", "lete", "leat", "l33t")
MAX_ADJUST_POINTS = 1000

_MENTION = re.compile(r"<@([UW][A-Z0-9]+)(?:\|[^>]*)?>")
_LABELED_LINK = re.compile(r"<(?![@#!])[^|>]+\|([^>]+)>")
_BARE_LINK = re.compile(r"<(?![@#!])([^>]+)>")
# "1. Two Sum", "1) Two Sum", "#1 Two Sum". A bare "24 Game" or "01 Matrix" keeps its number.
_LEADING_NUMBER = re.compile(r"^(?:#\d+[.):]?|\d+[.):])\s*")
_PROBLEM_URL = re.compile(r"/problems/([a-z0-9-]+)")


@dataclass(frozen=True)
class Command:
    name: str  # "board", "me" or "help"
    args: tuple[str, ...]


@dataclass(frozen=True)
class Adjust:
    sign: int  # +1 for "add", -1 for "remove"
    user_id: str
    points: int
    reason: str


@dataclass(frozen=True)
class AdjustUsageError:
    message: str


@dataclass(frozen=True)
class Solve:
    problem: str  # as the member typed it
    problem_key: str  # normalized, used to catch duplicates
    difficulty: str
    difficulty_given: bool

    @property
    def points(self) -> int:
        return DIFFICULTY_POINTS[self.difficulty]


Parsed = Command | Adjust | AdjustUsageError | Solve


def parse(text: str, has_image: bool) -> Parsed | None:
    """Return what a message means, or None if it isn't a "leet" message.

    With no screenshot, "leet board"/"leet me"/"leet help" are commands. With a screenshot,
    everything is a solve, so problems like "Add Binary" or "Remove Element" still log.
    Admin "leet add/remove @user ..." always needs a mention, so it never clashes with those.
    """
    tokens = _clean(text).split()
    if not tokens or tokens[0].lower().rstrip(":,.!") not in _PREFIXES:
        return None
    rest = tokens[1:]
    if len(rest) >= 2 and rest[0].lower() in ("add", "remove") and _MENTION.fullmatch(rest[1]):
        return _parse_adjust(rest)
    if not has_image:
        if not rest:
            return Command("help", ())
        # Typos only count when the command is the whole message, so "leet stars" isn't "leet stats"
        allow_typos = len(rest) == 1 or (len(rest) == 2 and rest[1].lower().startswith("all"))
        command = _match_command(rest[0], allow_typos)
        if command:
            return Command(command, tuple(word.lower() for word in rest[1:]))
    return _parse_solve(rest)


def normalize_problem(name: str) -> str:
    """"1. Two Sum", "two-sum" and "Two  Sum!" all become "two sum"."""
    key = name.strip().lower()
    url = _PROBLEM_URL.search(key)
    if url:
        key = url.group(1)  # a pasted LeetCode link counts as the same problem as its title
    key = _LEADING_NUMBER.sub("", key, count=1)
    key = re.sub(r"['’]", "", key)
    key = re.sub(r"[\W_]+", " ", key)
    return key.strip()


def _clean(text: str) -> str:
    """Undo Slack formatting: &amp; escapes, <url|label> links, <@U123|name> mentions."""
    text = html.unescape(text or "")
    text = _MENTION.sub(lambda m: f"<@{m.group(1)}>", text)
    text = _LABELED_LINK.sub(r"\1", text)
    return _BARE_LINK.sub(r"\1", text)


def _match_command(word: str, allow_typos: bool) -> str | None:
    word = word.lower().strip(":,.!?")
    for command, aliases in _COMMAND_ALIASES.items():
        for alias in aliases:
            fuzzy = allow_typos and len(alias) >= _FUZZY_MIN_LENGTH and _one_typo_apart(word, alias)
            if word == alias or fuzzy:
                return command
    return None


def _one_typo_apart(a: str, b: str) -> bool:
    """True if a and b differ by one insert, delete, substitution or swap of neighbours."""
    if a == b or abs(len(a) - len(b)) > 1:
        return False
    if len(a) == len(b):
        diffs = [i for i in range(len(a)) if a[i] != b[i]]
        if len(diffs) == 1:
            return True
        return len(diffs) == 2 and diffs[1] == diffs[0] + 1 and a[diffs[0]] == b[diffs[1]] and a[diffs[1]] == b[diffs[0]]
    shorter, longer = (a, b) if len(a) < len(b) else (b, a)
    return any(longer[:i] + longer[i + 1 :] == shorter for i in range(len(longer)))


def _parse_adjust(rest: list[str]) -> Adjust | AdjustUsageError:
    """Only called once parse() has checked rest[1] is a mention."""
    verb = rest[0].lower()
    usage = AdjustUsageError(f"Usage: `leet {verb} @person <points> <reason>`, e.g. `leet {verb} @alex 2 fake screenshot`")
    mention = _MENTION.fullmatch(rest[1])
    assert mention is not None
    amount = rest[2] if len(rest) >= 3 else ""
    if len(rest) < 4 or not (amount.isascii() and amount.isdigit()) or not 0 < int(amount) <= MAX_ADJUST_POINTS:
        return usage
    return Adjust(
        sign=1 if verb == "add" else -1,
        user_id=mention.group(1),
        points=int(amount),
        reason=" ".join(rest[3:]),
    )


def _parse_solve(rest: list[str]) -> Solve:
    difficulty = _ALIAS_TO_DIFFICULTY.get(rest[-1].lower().strip("()[]{}.,!:-")) if rest else None
    name_tokens = rest[:-1] if difficulty else rest
    problem = " ".join(name_tokens).strip(" -–—:,")
    return Solve(
        problem=problem,
        problem_key=normalize_problem(problem),
        difficulty=difficulty or DEFAULT_DIFFICULTY,
        difficulty_given=difficulty is not None,
    )
