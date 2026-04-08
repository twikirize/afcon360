# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
import redis
import os

# Core DB + migrations
db = SQLAlchemy()
migrate = Migrate()

# Auth/session
login_manager = LoginManager()
login_manager.login_view = "auth_routes.login"
login_manager.session_protection = "strong"

# CSRF protection for forms
csrf = CSRFProtect()

# Redis URL from environment
_redis_url = os.getenv("REDIS_URL", "redis://localhost:6379/0")

# Rate limiting with Redis storage
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["2000 per day", "500 per hour"],
    storage_uri=_redis_url,
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
)

# Caching with Redis
cache = Cache(config={
    "CACHE_TYPE": "RedisCache",
    "CACHE_REDIS_URL": _redis_url,
    "CACHE_DEFAULT_TIMEOUT": 300
})

# Redis client (lazy-loaded)
class LazyRedis:
    def __init__(self):
        self._client = None
        self._url = _redis_url

    @property
    def client(self):
        if self._client is None:
            self._client = redis.Redis.from_url(
                self._url,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            # Test connection
            self._client.ping()
        return self._client

    def __getattr__(self, name):
        return getattr(self.client, name)

redis_client = LazyRedis()
