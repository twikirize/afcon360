import os
import sys
import logging
import subprocess
import atexit
import threading

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


def _detect_lan_ipv4():
    """Return the outbound LAN IPv4 address, or None when unavailable."""
    import socket

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        sock.connect(("8.8.8.8", 80))
        return sock.getsockname()[0]
    except OSError:
        return None
    finally:
        sock.close()


def _metro_is_running():
    """Return True when Metro is already serving its status endpoint."""
    import urllib.request

    try:
        with urllib.request.urlopen("http://127.0.0.1:8081/status", timeout=2) as response:
            body = response.read(64).decode("utf-8", errors="replace")
            return response.status == 200 and "packager-status:running" in body
    except Exception:
        return False


def _stop_startall_dev_stack():
    """Evict a start-all-owned stack before PyCharm binds Flask and Metro."""
    if os.getenv("AFCON360_OWNER", "").strip().lower() != "pycharm":
        return
    if os.getenv("APP_ENV", "").strip().lower() != "phone-preview":
        return

    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    script = os.path.join(base_dir, "afcon360-user-dev", "stop-dev-stack.ps1")
    if not os.path.isfile(script):
        logger.warning("stop-dev-stack.ps1 not found at %s; continuing without cleanup", script)
        return

    logger.info("Stopping start-all dev stack (PyCharm owns this run)...")
    try:
        creationflags = subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0
        result = subprocess.run(
            [
                "powershell.exe",
                "-NoProfile",
                "-ExecutionPolicy", "Bypass",
                "-File", script,
                "-ExcludePid", str(os.getpid()),
            ],
            capture_output=True,
            text=True,
            timeout=30,
            creationflags=creationflags,
        )
        for line in (result.stdout or "").splitlines():
            logger.info("[STOP] %s", line)
        if result.returncode != 0:
            logger.warning("stop-dev-stack.ps1 exited %s", result.returncode)
            for line in (result.stderr or "").splitlines():
                logger.warning("[STOP] %s", line)
    except Exception as exc:
        logger.warning("Could not stop the start-all dev stack: %s", exc, exc_info=True)


def start_metro():
    """Start Metro bundler as a subprocess for dev client development."""
    global _metro_process
    
    logger.info(f"[METRO_DEBUG] AFCON360_DEVELOPMENT_CLIENT={os.getenv('AFCON360_DEVELOPMENT_CLIENT')}")
    logger.info(f"[METRO_DEBUG] METRO_AUTO_START={os.getenv('METRO_AUTO_START')}")
    
    # Only start Metro in development with dev client
    if not os.getenv('AFCON360_DEVELOPMENT_CLIENT', '').lower() in ('true', '1', 'yes'):
        logger.info("[METRO_DEBUG] AFCON360_DEVELOPMENT_CLIENT not set to true, skipping Metro")
        return
    
    if os.getenv('METRO_AUTO_START', '').lower() in ('false', '0', 'no'):
        logger.info("Metro auto-start disabled via METRO_AUTO_START=false")
        return

    if _metro_is_running():
        logger.info("Metro is already running on port 8081; reusing it.")
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
        flask_host = os.getenv('FLASK_HOST', '').strip()
        flask_port = os.getenv('FLASK_PORT', '5000')
        if flask_host in ('', '0.0.0.0', '::'):
            url_host = _detect_lan_ipv4() or '127.0.0.1'
        elif flask_host in ('127.0.0.1', 'localhost'):
            url_host = '127.0.0.1'
        else:
            url_host = flask_host
        api_base_url = f"http://{url_host}:{flask_port}"

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
        
        # Build absolute path to mobile/apps/user directory
        base_dir = os.path.dirname(os.path.dirname(__file__))
        metro_cwd = os.path.join(base_dir, 'afcon360-user-dev', 'mobile', 'apps', 'user')
        metro_cwd = os.path.abspath(metro_cwd)
        
        logger.info(f"[METRO_DEBUG] Metro script: {metro_script}")
        logger.info(f"[METRO_DEBUG] Metro working directory: {metro_cwd}")
        logger.info(f"[METRO_DEBUG] Metro script exists: {os.path.exists(metro_script)}")
        logger.info(f"[METRO_DEBUG] Metro cwd exists: {os.path.exists(metro_cwd)}")
        
        _metro_process = subprocess.Popen(
            metro_cmd,
            cwd=metro_cwd,
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
                if _metro_process and _metro_process.stdout:
                    for line in _metro_process.stdout:
                        logger.info(f"[METRO] {line.rstrip()}")
            except Exception:
                pass
        
        metro_thread = threading.Thread(target=read_metro_output, daemon=True)
        metro_thread.start()
        
        # Register cleanup
        def cleanup_metro():
            if _metro_process and _metro_process.poll() is None:
                logger.info("Stopping Metro...")
                try:
                    if sys.platform == 'win32':
                        subprocess.run(
                            ["taskkill.exe", "/PID", str(_metro_process.pid), "/T", "/F"],
                            capture_output=True,
                            check=False,
                        )
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
    if debug_mode and os.getenv('FLASK_ENV', 'production') == 'production':
        debug_mode = False
        logger.warning("FLASK_DEBUG=true but FLASK_ENV=production - Disabling debug mode for safety")

    # A PyCharm-owned run evicts the start-all-launched stack before binding.
    _stop_startall_dev_stack()

    # Auto-start Metro for development client
    if os.getenv('AFCON360_DEVELOPMENT_CLIENT', '').lower() in ('true', '1', 'yes'):
        start_metro()

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