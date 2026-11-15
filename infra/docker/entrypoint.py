"""Keep operator credentials/URL options; translate only hosts inside Compose."""

import os
import sys
from urllib.parse import urlsplit, urlunsplit

from sqlalchemy.engine import make_url

database = make_url(os.environ["DATABASE_URL"]).set(host="postgres", port=5432)
os.environ["DATABASE_URL"] = database.render_as_string(hide_password=False)
redis = urlsplit(os.environ["REDIS_URL"])
credentials = redis.netloc.rsplit("@", 1)[0] + "@" if "@" in redis.netloc else ""
os.environ["REDIS_URL"] = urlunsplit(redis._replace(netloc=credentials + "redis:6379"))
os.execvp(sys.argv[1], sys.argv[1:])
