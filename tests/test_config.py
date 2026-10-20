import pytest

from leetbot.config import load_config

VALID = {
    "SLACK_BOT_TOKEN": "xoxb-1",
    "SLACK_SIGNING_SECRET": "s",
    "LEET_CHANNEL_ID": "C1",
    "DATABASE_URL": "postgresql://x",
    "CRON_SECRET": "c" * 20,
    "ADMIN_SLACK_IDS": " U1, U2 ,,",
}


def test_loads_and_parses_admins():
    config = load_config(VALID)
    assert config.channel_id == "C1"
    assert config.admin_ids == frozenset({"U1", "U2"})


def test_admins_optional():
    assert load_config({k: v for k, v in VALID.items() if k != "ADMIN_SLACK_IDS"}).admin_ids == frozenset()


def test_missing_vars_are_named():
    with pytest.raises(RuntimeError, match="LEET_CHANNEL_ID, DATABASE_URL"):
        load_config({**VALID, "LEET_CHANNEL_ID": " ", "DATABASE_URL": ""})


def test_short_cron_secret_rejected():
    with pytest.raises(RuntimeError, match="CRON_SECRET"):
        load_config({**VALID, "CRON_SECRET": "short"})
