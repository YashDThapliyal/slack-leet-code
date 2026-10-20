"""HTTP routes: Slack events, secret-protected cron triggers, and a health check."""

import hmac
import logging

from flask import Flask, jsonify, request
from slack_bolt import App
from slack_bolt.adapter.flask import SlackRequestHandler

from leetbot.config import Config
from leetbot.dates import pacific_today
from leetbot.handlers import handle_message
from leetbot.posts import JOBS
from leetbot.store import Store

logger = logging.getLogger(__name__)


def create_app(config: Config, store: Store, verify_slack_token: bool = True) -> Flask:
    store.init_schema()
    bolt = App(
        token=config.slack_bot_token,
        signing_secret=config.slack_signing_secret,
        token_verification_enabled=verify_slack_token,
    )

    @bolt.event("message")
    def on_message(event, body, client):
        handle_message(event, body.get("event_id", ""), client, config, store)

    slack_handler = SlackRequestHandler(bolt)
    flask_app = Flask(__name__)

    @flask_app.post("/slack/events")
    def slack_events():
        return slack_handler.handle(request)

    @flask_app.post("/cron/<job>")
    def cron(job: str):
        secret = request.headers.get("X-Cron-Secret", "")
        if not hmac.compare_digest(secret.encode(), config.cron_secret.encode()):
            return jsonify(ok=False, error="forbidden"), 403
        run = JOBS.get(job)
        if run is None:
            return jsonify(ok=False, error=f"unknown job, use one of: {', '.join(JOBS)}"), 404
        try:
            result = run(bolt.client, config, store, pacific_today())
        except Exception:
            logger.exception("Cron job %s failed", job)
            return jsonify(ok=False, error="job failed, check the Render logs"), 500
        return jsonify(ok=True, job=job, result=result)

    @flask_app.get("/health")
    def health():
        return "ok", 200

    return flask_app
