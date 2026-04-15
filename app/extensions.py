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

# Redis URL from environment - will be validated in create_app
# Use a placeholder that will be replaced when app is initialized
_redis_url = None

# Rate limiting - storage_uri will be configured in create_app
# Don't set storage_uri here to avoid defaulting to memory://
limiter = Limiter(
    key_func=get_remote_address,
    default_limits=["2000 per day", "500 per hour"],
    storage_options={"socket_connect_timeout": 30},
    strategy="fixed-window",
)

# Caching with Redis - will be configured in create_app
cache = Cache(config={
    "CACHE_TYPE": "SimpleCache",  # Default to SimpleCache, will be updated in create_app
    "CACHE_DEFAULT_TIMEOUT": 300
})

# Redis client (lazy-loaded) - will be configured in create_app
class LazyRedis:
    def __init__(self):
        self._client = None
        self._url = None

    def configure(self, redis_url: str):
        """Configure Redis URL after app config is loaded"""
        self._url = redis_url
        self._client = None  # Reset client to force reconnection with new URL

    @property
    def client(self):
        if self._client is None:
            if not self._url:
                raise RuntimeError(
                    "Redis URL not configured. Call configure() method first. "
                    "This should be done in create_app() function."
                )
            self._client = redis.Redis.from_url(
                self._url,
                decode_responses=False,
                socket_connect_timeout=5,
                socket_keepalive=True
            )
            # Test connection
            try:
                self._client.ping()
            except Exception as e:
                raise RuntimeError(f"Failed to connect to Redis at {self._url}: {e}")
        return self._client

    def __getattr__(self, name):
        return getattr(self.client, name)

redis_client = LazyRedis()
