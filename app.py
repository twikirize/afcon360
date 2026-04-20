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
    app.run(debug=True, use_reloader=False)#Remove the reloader later if necessary
