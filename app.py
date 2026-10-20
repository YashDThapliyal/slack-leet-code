"""Entry point. Production: gunicorn app:flask_app. Local: python app.py"""

import logging
import os

from leetbot.config import load_config
from leetbot.store import Store
from leetbot.web import create_app

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")

config = load_config()
flask_app = create_app(config, Store(config.database_url))

if __name__ == "__main__":
    flask_app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 3000)))
