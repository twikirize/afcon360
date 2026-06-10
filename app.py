import os
import sys
import time
import logging

import os

print("APP_ENV =", os.getenv("APP_ENV"))
print("FLASK_ENV =", os.getenv("FLASK_ENV"))
#print("DATABASE_URL =", os.getenv("DATABASE_URL"))
print("REDIS_URL =", os.getenv("REDIS_URL"))


# Setup logging to show errors in console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # This sends logs to console/shell
    ]
)
logger = logging.getLogger(__name__)

# Only show path debug when troubleshooting (set SHOW_PATH_DEBUG=true)
if os.getenv('SHOW_PATH_DEBUG', 'false').lower() == 'true':
    logger.info("=== Startup Debug Info ===")
    logger.info(f"sys.path: {sys.path}")
    logger.info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'not set')}")
    try:
        import app

        logger.info(f"app.__file__: {getattr(app, '__file__', 'NO FILE')}")
        logger.info(f"has create_app: {hasattr(app, 'create_app')}")
    except Exception as e:
        logger.error(f"import app failed: {e}")
    logger.info("=== End Debug Info ===")

# Always show startup time
logger.info(f"App starting at: {time.time()}")

from app import create_app
from app.config import Config

try:
    app = create_app()
    logger.info("Application created successfully")
except Exception as e:
    logger.error(f"Failed to create app: {e}", exc_info=True)
    raise

app.config['REQUIRE_EMAIL_VERIFICATION'] = Config.REQUIRE_EMAIL_VERIFICATION


@app.context_processor
def inject_config():
    return dict(config=app.config)


if __name__ == "__main__":
    import os

    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() in ('true', '1', 'yes')
    if debug_mode and os.getenv('FLASK_ENV', 'production') == 'production':
        debug_mode = False
        logger.warning("FLASK_DEBUG=true but FLASK_ENV=production - Disabling debug mode for safety")

    # Log environment info
    logger.info(f"Environment: {os.getenv('FLASK_ENV', 'production')}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.info(f"Host: {os.getenv('FLASK_HOST', '127.0.0.1')}")
    logger.info(f"Port: {os.getenv('FLASK_PORT', '5000')}")

    try:
        app.run(
            debug=debug_mode,
            use_reloader=False,
            host=os.getenv('FLASK_HOST', '127.0.0.1'),
            port=int(os.getenv('FLASK_PORT', '5000'))
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise