import hashlib
import hmac
import json
import threading
import time

import pytest
from slack_sdk import WebClient
from slack_sdk.web import SlackResponse

from leetbot import posts, web
from leetbot.web import create_app


@pytest.fixture
def http(config, store, monkeypatch):
    calls = []
    monkeypatch.setitem(posts.JOBS, "morning", lambda client, cfg, st, today: calls.append(today) or "posted")
    app = create_app(config, store, verify_slack_token=False)
    return app.test_client(), calls


def test_cron_requires_secret(http):
    client, calls = http
    assert client.post("/cron/morning").status_code == 403
    assert client.post("/cron/morning", headers={"X-Cron-Secret": "wrong"}).status_code == 403
    assert calls == []


def test_cron_runs_job(http, config):
    client, calls = http
    response = client.post("/cron/morning", headers={"X-Cron-Secret": config.cron_secret})
    assert response.status_code == 200
    assert response.get_json() == {"ok": True, "job": "morning", "result": "posted"}
    assert len(calls) == 1


def test_unknown_job(http, config):
    client, _ = http
    assert client.post("/cron/lunch", headers={"X-Cron-Secret": config.cron_secret}).status_code == 404


def test_health(http):
    client, _ = http
    assert client.get("/health").data == b"ok"


def test_signed_slack_event_reaches_handler(config, store, monkeypatch):
    received = threading.Event()
    calls = []

    def fake_handle(event, event_id, client, cfg, st):
        calls.append((event["text"], event_id))
        received.set()

    monkeypatch.setattr(web, "handle_message", fake_handle)
    # Bolt verifies the bot token with Slack on each request; answer for Slack so the test stays offline
    monkeypatch.setattr(
        WebClient,
        "auth_test",
        lambda self, **kw: SlackResponse(
            client=self, http_verb="POST", api_url="auth.test", req_args={}, headers={}, status_code=200,
            data={"ok": True, "team_id": "T1", "user_id": "UBOT", "bot_id": "B1"},
        ),
    )
    http = create_app(config, store, verify_slack_token=False).test_client()
    body = json.dumps({
        "type": "event_callback", "team_id": "T1", "api_app_id": "A1", "event_id": "Ev123",
        "event": {"type": "message", "channel": "C_LEET", "user": "U1", "text": "leet board", "ts": "1.000001"},
    })
    timestamp = str(int(time.time()))
    signature = "v0=" + hmac.new(config.slack_signing_secret.encode(), f"v0:{timestamp}:{body}".encode(), hashlib.sha256).hexdigest()
    response = http.post("/slack/events", data=body, content_type="application/json",
                         headers={"X-Slack-Request-Timestamp": timestamp, "X-Slack-Signature": signature})
    assert response.status_code == 200
    assert received.wait(5)
    assert calls == [("leet board", "Ev123")]


def test_unsigned_slack_event_rejected(config, store):
    http = create_app(config, store, verify_slack_token=False).test_client()
    assert http.post("/slack/events", data="{}", content_type="application/json").status_code == 401
