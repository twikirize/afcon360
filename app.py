# app.py
import time#Jus to determine howlong the app takes to start / Enable reloader to know the  difference in the time takes to start
print("App starting at:", time.time())

from app import create_app
import config

app = create_app()

# Make sure the app's config has our custom settings
app.config['REQUIRE_EMAIL_VERIFICATION'] = config.REQUIRE_EMAIL_VERIFICATION

# Context processor to make config available in templates
@app.context_processor
def inject_config():
    return dict(config=app.config)

if __name__ == "__main__":
    import os
    # SECURITY: Never run with debug=True in production
    # Set FLASK_DEBUG=true only in development environment
    debug_mode = os.getenv('FLASK_DEBUG', 'true').lower() in ('true', '1', 'yes')
    if debug_mode and os.getenv('FLASK_ENV', 'production') == 'production':
        print("WARNING: FLASK_DEBUG is enabled but FLASK_ENV is production. Disabling debug mode for safety.")
        debug_mode = False
    app.run(debug=debug_mode, use_reloader=False)
