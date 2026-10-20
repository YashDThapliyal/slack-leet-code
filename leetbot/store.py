"""All database access. Each call opens a short-lived connection, which suits Neon's
scale-to-zero Postgres and a bot that handles a few requests a minute."""

from collections import defaultdict
from dataclasses import dataclass
from datetime import date

import psycopg

from leetbot.stats import Total

SCHEMA = """
CREATE TABLE IF NOT EXISTS solves (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    user_name   TEXT NOT NULL,
    problem     TEXT NOT NULL,
    problem_key TEXT NOT NULL,
    difficulty  TEXT NOT NULL CHECK (difficulty IN ('easy', 'medium', 'hard')),
    points      INTEGER NOT NULL,
    solve_date  DATE NOT NULL,
    slack_ts    TEXT NOT NULL UNIQUE,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (user_id, problem_key)
);
CREATE TABLE IF NOT EXISTS adjustments (
    id          BIGSERIAL PRIMARY KEY,
    user_id     TEXT NOT NULL,
    user_name   TEXT NOT NULL,
    points      INTEGER NOT NULL,
    reason      TEXT NOT NULL,
    admin_id    TEXT NOT NULL,
    adjust_date DATE NOT NULL,
    created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE TABLE IF NOT EXISTS daily_posts (
    kind       TEXT NOT NULL,
    post_date  DATE NOT NULL,
    slack_ts   TEXT,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
    PRIMARY KEY (kind, post_date)
);
CREATE TABLE IF NOT EXISTS processed_events (
    event_id   TEXT PRIMARY KEY,
    created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
"""

# Points from solves and admin adjustments, optionally limited to a date range. Names: the latest
# real one wins; a raw user ID (stored when Slack's name lookup failed) is only used as a last resort.
_TOTALS_SQL = """
WITH entries AS (
    SELECT user_id, user_name, points, created_at, solve_date AS day FROM solves
    UNION ALL
    SELECT user_id, user_name, points, created_at, adjust_date AS day FROM adjustments
)
SELECT user_id, (array_agg(user_name ORDER BY user_name = user_id, created_at DESC))[1], SUM(points)
FROM entries
WHERE (%(start)s::date IS NULL OR day >= %(start)s) AND (%(end)s::date IS NULL OR day <= %(end)s)
GROUP BY user_id
"""

EVENT_RETENTION_DAYS = 7
STALE_CLAIM_SECONDS = 120


@dataclass(frozen=True)
class SolveRecord:
    user_id: str
    user_name: str
    problem: str
    problem_key: str
    difficulty: str
    points: int
    solve_date: date
    slack_ts: str


@dataclass(frozen=True)
class DayStatus:
    user_id: str
    name: str
    solved: bool


class Store:
    def __init__(self, database_url: str):
        self._url = database_url

    def _connect(self) -> psycopg.Connection:
        return psycopg.connect(self._url, connect_timeout=10)

    def init_schema(self) -> None:
        with self._connect() as conn:
            conn.execute(SCHEMA)

    # ---- Slack retry and cron dedupe ----

    def claim_event(self, event_id: str) -> bool:
        """True the first time an event is seen; False for Slack's retries of it."""
        with self._connect() as conn:
            row = conn.execute(
                "INSERT INTO processed_events (event_id) VALUES (%s) ON CONFLICT DO NOTHING RETURNING event_id",
                (event_id,),
            ).fetchone()
        return row is not None

    def prune_events(self) -> None:
        with self._connect() as conn:
            conn.execute(
                "DELETE FROM processed_events WHERE created_at < now() - make_interval(days => %s)",
                (EVENT_RETENTION_DAYS,),
            )

    def claim_post(self, kind: str, post_date: date) -> bool:
        """True if this scheduled post hasn't been made yet today; claims it so a cron retry won't repost.

        A claim that never got its Slack ts (the process died mid-post) can be reclaimed after a
        couple of minutes, so the backup cron run still posts instead of skipping forever.
        """
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO daily_posts (kind, post_date) VALUES (%s, %s)
                ON CONFLICT (kind, post_date) DO UPDATE SET created_at = now()
                WHERE daily_posts.slack_ts IS NULL
                  AND daily_posts.created_at < now() - make_interval(secs => %s)
                RETURNING kind
                """,
                (kind, post_date, STALE_CLAIM_SECONDS),
            ).fetchone()
        return row is not None

    def release_post(self, kind: str, post_date: date) -> None:
        """Undo a claim when posting failed, so the next cron attempt can try again."""
        with self._connect() as conn:
            conn.execute("DELETE FROM daily_posts WHERE kind = %s AND post_date = %s", (kind, post_date))

    def set_post_ts(self, kind: str, post_date: date, slack_ts: str) -> None:
        with self._connect() as conn:
            conn.execute(
                "UPDATE daily_posts SET slack_ts = %s WHERE kind = %s AND post_date = %s",
                (slack_ts, kind, post_date),
            )

    def is_daily_thread(self, thread_ts: str, post_dates: list[date]) -> bool:
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM daily_posts WHERE kind = 'morning' AND slack_ts = %s AND post_date = ANY(%s)",
                (thread_ts, post_dates),
            ).fetchone()
        return row is not None

    # ---- Points ----

    def add_solve(self, solve: SolveRecord) -> bool:
        """False if this person already logged this problem (or Slack resent the message)."""
        with self._connect() as conn:
            row = conn.execute(
                """
                INSERT INTO solves (user_id, user_name, problem, problem_key, difficulty, points, solve_date, slack_ts)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                ON CONFLICT DO NOTHING RETURNING id
                """,
                (
                    solve.user_id,
                    solve.user_name,
                    solve.problem,
                    solve.problem_key,
                    solve.difficulty,
                    solve.points,
                    solve.solve_date,
                    solve.slack_ts,
                ),
            ).fetchone()
        return row is not None

    def add_adjustment(
        self, user_id: str, user_name: str, points: int, reason: str, admin_id: str, adjust_date: date
    ) -> None:
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO adjustments (user_id, user_name, points, reason, admin_id, adjust_date)
                VALUES (%s, %s, %s, %s, %s, %s)
                """,
                (user_id, user_name, points, reason, admin_id, adjust_date),
            )

    def totals(self, start: date | None = None, end: date | None = None) -> list[Total]:
        with self._connect() as conn:
            rows = conn.execute(_TOTALS_SQL, {"start": start, "end": end}).fetchall()
        return [Total(user_id=uid, name=name, points=int(points)) for uid, name, points in rows]

    def solve_days(self) -> dict[str, set[date]]:
        """Every Pacific date each person logged at least one solve."""
        with self._connect() as conn:
            rows = conn.execute("SELECT DISTINCT user_id, solve_date FROM solves").fetchall()
        days = defaultdict(set)
        for user_id, day in rows:
            days[user_id].add(day)
        return dict(days)

    def difficulty_counts(self, user_id: str) -> dict[str, int]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT difficulty, COUNT(*) FROM solves WHERE user_id = %s GROUP BY difficulty", (user_id,)
            ).fetchall()
        return {difficulty: int(count) for difficulty, count in rows}

    def day_status(self, day: date) -> list[DayStatus]:
        """Everyone who has ever logged a solve, and whether they logged one on `day`."""
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT user_id, (array_agg(user_name ORDER BY user_name = user_id, created_at DESC))[1], bool_or(solve_date = %s)
                FROM solves GROUP BY user_id
                """,
                (day,),
            ).fetchall()
        return [DayStatus(user_id=uid, name=name, solved=solved) for uid, name, solved in rows]
