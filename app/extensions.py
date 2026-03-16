# app/extensions.py
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_login import LoginManager
from flask_wtf import CSRFProtect
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_caching import Cache
import redis

# Core DB + migrations
db = SQLAlchemy()
migrate = Migrate()

# Auth/session
login_manager = LoginManager()
login_manager.login_view = "auth_routes.login"
login_manager.session_protection = "strong"

# CSRF protection for forms
csrf = CSRFProtect()

# Rate limiting (create unbound; init in factory)
limiter = Limiter(key_func=get_remote_address, default_limits=[])

# Caching
cache = Cache(config={"CACHE_TYPE": "SimpleCache"})

# Caching
#cache = Cache(config={"CACHE_TYPE": "RedisCache", "CACHE_REDIS_URL": "redis://localhost:6379/0"}) #

# or RedisCache if you want Redis
#Redis client
redis_client = redis.Redis(host="localhost", port=6379, db=0)


# Optional: add other shared extensions here (e.g., mail, cache)
# from flask_mail import Mail
# mail = Mail()