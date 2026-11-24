import os
import sys
import logging
import subprocess
import atexit
import signal

# Environment information is printed by create_app() after configuration
# resolution, so it reflects what the application actually loaded.

# Setup logging to show errors in console
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler()  # This sends logs to console/shell
    ]
)
logger = logging.getLogger(__name__)

# Global reference to Metro subprocess
_metro_process = None

def start_metro():
    """Start Metro bundler as a subprocess for dev client development."""
    global _metro_process
    
    # Only start Metro in development with dev client
    if not os.getenv('AFCON360_DEVELOPMENT_CLIENT', '').lower() in ('true', '1', 'yes'):
        return
    
    if os.getenv('METRO_AUTO_START', '').lower() in ('false', '0', 'no'):
        logger.info("Metro auto-start disabled via METRO_AUTO_START=false")
        return
    
    # The mobile app is in a sibling directory: ../afcon360-user-dev/mobile
    base_dir = os.path.dirname(os.path.dirname(__file__))
    mobile_root = os.path.join(base_dir, 'afcon360-user-dev', 'mobile')
    metro_script = os.path.join(mobile_root, 'scripts', 'windows', 'start-user-metro.ps1')
    
    if not os.path.exists(metro_script):
        logger.warning(f"Metro script not found at {metro_script}, skipping Metro auto-start")
        return
    
    # Determine API base URL - use the one from environment or auto-detect
    api_base_url = os.getenv('EXPO_PUBLIC_API_BASE_URL')
    if not api_base_url:
        # Try to detect from Flask host/port
        flask_host = os.getenv('FLASK_HOST', '0.0.0.0')
        flask_port = os.getenv('FLASK_PORT', '5000')
        if flask_host in ('0.0.0.0', '::', '127.0.0.1', 'localhost'):
            api_base_url = f"http://127.0.0.1:{os.getenv('FLASK_PORT', '5000')}"
        else:
            api_base_url = f"http://{flask_host}:{os.getenv('FLASK_PORT', '5000')}"
    
    logger.info(f"Starting Metro dev client (API: {api_base_url})...")
    
    try:
        env = os.environ.copy()
        env.update({
            'AFCON360_PREVIEW_BUILD': 'true',
            'AFCON360_RELEASE_BUILD': 'false',
            'AFCON360_DEVELOPMENT_CLIENT': 'true',
            'AFCON360_UPDATE_CHANNEL': 'user-development-client',
            'EXPO_PUBLIC_API_BASE_URL': api_base_url,
        })
        
        # Use the PowerShell script to start Metro
        metro_cmd = [
            'powershell.exe',
            '-ExecutionPolicy', 'Bypass',
            '-File', os.path.abspath(metro_script),
            '-ConnectionMode', 'Lan',
            '-ApiBaseUrl', api_base_url,
        ]
        
        _metro_process = subprocess.Popen(
            metro_cmd,
            cwd=os.path.join(os.path.dirname(metro_script), '..', 'apps', 'user'),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            bufsize=1,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        
        # Start a thread to read Metro output
        def read_metro_output():
            try:
                for line in _metro_process.stdout:
                    logger.info(f"[METRO] {line.rstrip()}")
            except Exception:
                pass
        
        import threading
        metro_thread = threading.Thread(target=read_metro_output, daemon=True)
        metro_thread.start()
        
        # Register cleanup
        def cleanup_metro():
            if _metro_process and _metro_process.poll() is None:
                logger.info("Stopping Metro...")
                try:
                    if sys.platform == 'win32':
                        _metro_process.send_signal(signal.CTRL_BREAK_EVENT)
                    else:
                        _metro_process.terminate()
                    _metro_process.wait(timeout=5)
                except Exception:
                    try:
                        _metro_process.kill()
                    except Exception:
                        pass
        
        atexit.register(cleanup_metro)
        
        logger.info(f"Metro started (PID: {_metro_process.pid})")
        
    except Exception as e:
        logger.error(f"Failed to start Metro: {e}")
        _metro_process = None

# Only show path debug when troubleshooting (set SHOW_PATH_DEBUG=true)
if os.getenv('SHOW_PATH_DEBUG', 'false').lower() == 'true':
    logger.info("=== Startup Debug Info ===")
    logger.info(f"sys.path: {sys.path}")
    logger.info(f"PYTHONPATH: {os.environ.get('PYTHONPATH', 'not set')}")
    try:
        import app as afcon_app

        logger.info(f"app.__file__: {getattr(afcon_app, '__file__', 'NO FILE')}")
        logger.info(f"has create_app: {hasattr(afcon_app, 'create_app')}")
    except Exception as e:
        logger.error(f"import app failed: {e}")
    logger.info("=== End Debug Info ===")

from app import create_app
from app.config import Config
from app.extensions import socketio

try:
    app = create_app()
    logger.info("Application created successfully")
except Exception as e:
    logger.error(f"Failed to create app: {e}", exc_info=True)
    raise

logger.info("Application ready")

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
    
    # Auto-start Metro for development client
    if os.getenv('AFCON360_DEVELOPMENT_CLIENT', '').lower() in ('true', '1', 'yes'):
        start_metro()
    if debug_mode and os.getenv('FLASK_ENV', 'production') == 'production':
        debug_mode = False
        logger.warning("FLASK_DEBUG=true but FLASK_ENV=production - Disabling debug mode for safety")

    # --- Local-development TLS: FLASK_SSL = none | selfsigned | cert | devca ---
    # See dev_tls.py. Production TLS termination is out of scope (BACKLOG.md).
    from dev_tls import resolve_ssl_mode, detect_lan_ipv4s

    try:
        ssl_mode = resolve_ssl_mode(os.getenv('FLASK_SSL', 'none'))
    except ValueError as exc:
        logger.error(str(exc))
        raise SystemExit(2)
    ssl_enabled = ssl_mode != ''
    ssl_run_kwargs = {}

    if ssl_enabled:
        from dev_tls import build_ssl_context, ensure_devca, ensure_selfsigned

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
    # SECURITY: When debug=True, never bind 0.0.0.0 unless explicitly allowed via
    # ALLOW_LAN_DEBUG=1 — Werkzeug debugger exposes RCE on LAN.
    host = os.getenv('FLASK_HOST', '').strip()
    if not host:
        if debug_mode and os.getenv('ALLOW_LAN_DEBUG', '').strip().lower() not in ('1', 'true', 'yes'):
            host = '127.0.0.1'
        else:
            host = '0.0.0.0' if ssl_enabled else '127.0.0.1'
    port = int(os.getenv('FLASK_PORT', '5000'))

    if ssl_enabled and host in ('127.0.0.1', 'localhost', '::1'):
        logger.warning(
            f"FLASK_SSL enabled but FLASK_HOST={host} — a phone on the LAN CANNOT connect. "
            f"Set FLASK_HOST=0.0.0.0 (or unset it)."
        )

    # Server binding. Environment, database and extension information is
    # printed by create_app(); this block reports the reachable listening URLs.
    if ssl_enabled:
        logger.info(f"TLS mode: {ssl_mode}")
        urls = [f"https://localhost:{port}/"]
        urls += [f"https://{ip}:{port}/" for ip in detect_lan_ipv4s()]
        logger.info("Server listening:")
        for url in urls:
            logger.info(f"  {url}")
        if ssl_mode == 'devca':
            logger.info(
                "→ On your phone: install certs/dev-ca-cert.pem as a trusted CA once."
            )
        else:
            logger.info("→ On your phone: accept the self-signed warning.")
    else:
        if host in ('0.0.0.0', '::'):
            urls = [f"http://127.0.0.1:{port}/"]
            urls += [f"http://{ip}:{port}/" for ip in detect_lan_ipv4s()]
        else:
            urls = [f"http://{host}:{port}/"]
        logger.info("Server listening:")
        for url in urls:
            logger.info(f"  {url}")

    try:
        socketio.run(
            app,
            debug=debug_mode,
            use_reloader=False,
            host=host,
            port=port,
            allow_unsafe_werkzeug=True,
            **ssl_run_kwargs
        )
    except Exception as e:
        logger.error(f"Failed to start server: {e}", exc_info=True)
        raise