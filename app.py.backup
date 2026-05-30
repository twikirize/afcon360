import sys
import os
print("=== DEBUG ===")
print("sys.path:", sys.path)
print("PYTHONPATH:", os.environ.get('PYTHONPATH', 'not set'))
try:
    import app
    print("app.__file__:", getattr(app, '__file__', 'NO FILE'))
    print("has create_app:", hasattr(app, 'create_app'))
except Exception as e:
    print("import app failed:", e)
print("=== END DEBUG ===")

import time
print("App starting at:", time.time())
from app import create_app
from app.config import Config
app = create_app()

app.config['REQUIRE_EMAIL_VERIFICATION'] = Config.REQUIRE_EMAIL_VERIFICATION

@app.context_processor
def inject_config():
    return dict(config=app.config)

if __name__ == "__main__":
    import os
    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() in ('true', '1', 'yes')
    if debug_mode and os.getenv('FLASK_ENV', 'production') == 'production':
        debug_mode = False
    app.run(debug=debug_mode, use_reloader=False)
