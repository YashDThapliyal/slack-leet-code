"""All settings come from environment variables so nobody has to edit code to change them."""

import os
from dataclasses import dataclass

REQUIRED = (
    "SLACK_BOT_TOKEN",
    "SLACK_SIGNING_SECRET",
    "LEET_CHANNEL_ID",
    "DATABASE_URL",
    "CRON_SECRET",
)
MIN_CRON_SECRET_LENGTH = 16


@dataclass(frozen=True)
class Config:
    slack_bot_token: str
    slack_signing_secret: str
    channel_id: str
    admin_ids: frozenset[str]
    database_url: str
    cron_secret: str


def load_config(env=os.environ) -> Config:
    """Read and validate settings. Fails fast with a message naming what's missing."""
    missing = [key for key in REQUIRED if not env.get(key, "").strip()]
    if missing:
        raise RuntimeError(f"Missing required environment variables: {', '.join(missing)}")
    cron_secret = env["CRON_SECRET"].strip()
    if len(cron_secret) < MIN_CRON_SECRET_LENGTH:
        raise RuntimeError(f"CRON_SECRET must be at least {MIN_CRON_SECRET_LENGTH} characters long")
    admin_ids = frozenset(uid.strip() for uid in env.get("ADMIN_SLACK_IDS", "").split(",") if uid.strip())
    return Config(
        slack_bot_token=env["SLACK_BOT_TOKEN"].strip(),
        slack_signing_secret=env["SLACK_SIGNING_SECRET"].strip(),
        channel_id=env["LEET_CHANNEL_ID"].strip(),
        admin_ids=admin_ids,
        database_url=env["DATABASE_URL"].strip(),
        cron_secret=cron_secret,
    )
