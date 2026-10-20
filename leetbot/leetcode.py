"""Fetch LeetCode's daily problem. Failures return None so the morning ping still goes out."""

import json
import logging
import urllib.request
from dataclasses import dataclass

logger = logging.getLogger(__name__)

GRAPHQL_URL = "https://leetcode.com/graphql"
_QUERY = "{ activeDailyCodingChallengeQuestion { link question { title difficulty } } }"
TIMEOUT_SECONDS = 10


@dataclass(frozen=True)
class DailyProblem:
    title: str
    difficulty: str
    url: str


def fetch_daily_problem() -> DailyProblem | None:
    request = urllib.request.Request(
        GRAPHQL_URL,
        data=json.dumps({"query": _QUERY}).encode(),
        headers={"Content-Type": "application/json", "Referer": "https://leetcode.com", "User-Agent": "Mozilla/5.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT_SECONDS) as response:
            daily = json.load(response)["data"]["activeDailyCodingChallengeQuestion"]
        return DailyProblem(
            title=daily["question"]["title"],
            difficulty=daily["question"]["difficulty"],
            url="https://leetcode.com" + daily["link"],
        )
    except Exception:
        logger.warning("Couldn't fetch LeetCode's daily problem; posting the ping without it", exc_info=True)
        return None
