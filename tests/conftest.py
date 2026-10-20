"""Shared fixtures. Database tests need TEST_DATABASE_URL pointing at a throwaway Postgres
database (its tables get wiped); without it they're skipped."""

import os
from datetime import date, datetime, time

import psycopg
import pytest

from leetbot.config import Config
from leetbot.dates import PACIFIC
from leetbot.store import Store

CHANNEL = "C_LEET"
ADMIN = "U0ADMIN"


@pytest.fixture
def config() -> Config:
    return Config(
        slack_bot_token="xoxb-test",
        slack_signing_secret="signing-secret",
        channel_id=CHANNEL,
        admin_ids=frozenset({ADMIN}),
        database_url=os.environ.get("TEST_DATABASE_URL", ""),
        cron_secret="a" * 32,
    )


@pytest.fixture
def store() -> Store:
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("TEST_DATABASE_URL not set")
    db = Store(url)
    db.init_schema()
    with psycopg.connect(url) as conn:
        conn.execute("TRUNCATE solves, adjustments, daily_posts, processed_events")
    return db


class FakeClient:
    """Records what the bot would send to Slack."""

    def __init__(self, names: dict[str, str] | None = None):
        self.names = names or {}
        self.posts: list[dict] = []
        self.reactions: list[dict] = []
        self._next_ts = 1000

    def chat_postMessage(self, **kwargs):
        self._next_ts += 1
        self.posts.append(kwargs)
        return {"ok": True, "ts": f"{self._next_ts}.000001"}

    def reactions_add(self, **kwargs):
        self.reactions.append(kwargs)
        return {"ok": True}

    def users_info(self, user: str):
        return {"ok": True, "user": {"profile": {"display_name": self.names.get(user, ""), "real_name": user}}}

    def texts(self) -> list[str]:
        return [p["text"] for p in self.posts]


@pytest.fixture
def client() -> FakeClient:
    return FakeClient({"U0ALICE": "alice", "U0BOB": "bob", "U0CARA": "cara", ADMIN: "admin"})


def slack_ts(day: date, hour: int = 12, minute: int = 0) -> str:
    """A Slack timestamp for a Pacific day and time."""
    return f"{datetime.combine(day, time(hour, minute), tzinfo=PACIFIC).timestamp():.6f}"
