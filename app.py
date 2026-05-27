import os
import time

print("App starting at:", time.time())

from app import create_app
from app.config import Config

# =========================
# Create app
# =========================
app = create_app()

# Inject config into templates
app.config['REQUIRE_EMAIL_VERIFICATION'] = Config.REQUIRE_EMAIL_VERIFICATION


@app.context_processor
def inject_config():
    return dict(config=app.config)


# =========================
# ENVIRONMENT SETUP
# =========================
ENV = os.getenv("FLASK_ENV", "development").lower()
DEBUG = os.getenv("FLASK_DEBUG", "true").lower() in ("true", "1", "yes")
PORT = int(os.getenv("PORT", 5000))

IS_PRODUCTION = ENV == "production"

# Force safety rules in production
if IS_PRODUCTION:
    DEBUG = False


# =========================
# MAIN RUN
# =========================
if __name__ == "__main__":

    HOST = "127.0.0.1"

    # Allow external access only in production
    if IS_PRODUCTION:
        HOST = "0.0.0.0"

    print(f"Running in {ENV} mode")
    print(f"Debug: {DEBUG}")
    print(f"Host: {HOST}")
    print(f"Port: {PORT}")

    app.run(
        host=HOST,
        port=PORT,
        debug=DEBUG,
        use_reloader=(not IS_PRODUCTION)
    )