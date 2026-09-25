import os
import sys
import time
import logging

import os

print("APP_ENV =", os.getenv("APP_ENV"))
print("FLASK_ENV =", os.getenv("FLASK_ENV"))
#print("DATABASE_URL =", os.getenv("DATABASE_URL"))
print("REDIS_URL set:", bool(os.getenv("REDIS_URL")))


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
from app.extensions import socketio

try:
    app = create_app()
    logger.info("Application created successfully")
except Exception as e:
    logger.error(f"Failed to create app: {e}", exc_info=True)
    raise

app.config['REQUIRE_EMAIL_VERIFICATION'] = Config.REQUIRE_EMAIL_VERIFICATION


@app.template_filter('strftime')
def strftime_filter(value, fmt):
    if value is None:
        return ''
    return value.strftime(fmt)


@app.context_processor
def inject_config():
    return dict(config=app.config)


if __name__ == "__main__":
    import os

    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() in ('true', '1', 'yes')
    if debug_mode and os.getenv('FLASK_ENV', 'production') == 'production':
        debug_mode = False
        logger.warning("FLASK_DEBUG=true but FLASK_ENV=production - Disabling debug mode for safety")

    # --- Local-development TLS: FLASK_SSL = none | selfsigned | cert | devca ---
    # See dev_tls.py. Production TLS termination is out of scope (BACKLOG.md).
    from dev_tls import resolve_ssl_mode

    try:
        ssl_mode = resolve_ssl_mode(os.getenv('FLASK_SSL', 'none'))
    except ValueError as exc:
        logger.error(str(exc))
        raise SystemExit(2)
    ssl_enabled = ssl_mode != ''
    ssl_run_kwargs = {}

    if ssl_enabled:
        from dev_tls import build_ssl_context, detect_lan_ipv4s, ensure_devca, ensure_selfsigned

        if ssl_mode == 'selfsigned':
            ssl_cert, ssl_key = ensure_selfsigned()
        elif ssl_mode == 'devca':
            ssl_cert, ssl_key = ensure_devca()
        else:  # ssl_mode == 'cert' — externally supplied pair, never overwritten
            ssl_cert = os.getenv('FLASK_SSL_CERT', '').strip()
            ssl_key = os.getenv('FLASK_SSL_KEY', '').strip()
            if not ssl_cert or not ssl_key:
                logger.error("FLASK_SSL=cert requires FLASK_SSL_CERT and FLASK_SSL_KEY to be set.")
                raise SystemExit(2)
        # Only passed when TLS is on: gevent 26.x crashes on ssl_context=None.
        ssl_run_kwargs['ssl_context'] = build_ssl_context(ssl_cert, ssl_key)

    # With TLS enabled and FLASK_HOST unset, bind all interfaces so a phone on
    # the LAN/hotspot can reach this machine (requirement: reachable, not 127.0.0.1).
    host = os.getenv('FLASK_HOST', '').strip()
    if not host:
        host = '0.0.0.0' if ssl_enabled else '127.0.0.1'
    port = int(os.getenv('FLASK_PORT', '5000'))

    if ssl_enabled and host in ('127.0.0.1', 'localhost', '::1'):
        logger.warning(
            f"FLASK_SSL enabled but FLASK_HOST={host} — a phone on the LAN CANNOT connect. "
            f"Set FLASK_HOST=0.0.0.0 (or unset it)."
        )

    # Log environment info
    logger.info(f"Environment: {os.getenv('FLASK_ENV', 'production')}")
    logger.info(f"Debug mode: {debug_mode}")
    logger.info(f"Host: {host}")
    logger.info(f"Port: {port}")
    if ssl_enabled:
        logger.info(f"TLS mode: {ssl_mode}")
        urls = [f"https://localhost:{port}/"]
        urls += [f"https://{ip}:{port}/" for ip in detect_lan_ipv4s()]
        if ssl_mode == 'devca':
            logger.info(
                "→ Open on your phone (install certs/dev-ca-cert.pem as a trusted CA once): "
                + "  ".join(urls)
            )
        else:
            logger.info("→ Open on your phone (accept the self-signed warning): " + "  ".join(urls))
    else:
        logger.info(f"→ Open your browser at http://{host}:{port}/")

    try:
        socketio.run(
            app,
            debug=debug_mode,
            use_reloader=False,
            host=host,
            port=port,
            **ssl_run_kwargs
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise