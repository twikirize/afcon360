
# app/routes.py

from flask import Blueprint, render_template
from config import APP_NAME

main_routes = Blueprint('main_routes', __name__)

@main_routes.route("/")
def home():
    return render_template("base.html", app_name=APP_NAME)

# Function to register blueprints with the app
def register_blueprints(app):
    """Register all blueprints with the Flask application"""
    # Register main routes
    app.register_blueprint(main_routes)

    # Import and register theme blueprint
    try:
        from app.tools.theme_routes import theme_bp
        app.register_blueprint(theme_bp)
        app.logger.info("Registered theme blueprint")
    except ImportError as e:
        app.logger.warning(f"Could not import theme blueprint: {e}")

    # Import and register role-specific blueprints
    try:
        from app.auditor.routes import auditor_bp
        app.register_blueprint(auditor_bp)
        app.logger.info("Registered auditor blueprint")
    except ImportError as e:
        app.logger.warning(f"Could not import auditor blueprint: {e}")

    try:
        from app.support.routes import support_bp
        app.register_blueprint(support_bp)
        app.logger.info("Registered support blueprint")
    except ImportError as e:
        app.logger.warning(f"Could not import support blueprint: {e}")

    try:
        from app.fan.routes import fan_bp
        app.register_blueprint(fan_bp)
        app.logger.info("Registered fan blueprint")
    except ImportError as e:
        app.logger.warning(f"Could not import fan blueprint: {e}")

    # Note: The fan blueprint is already registered above, but we need to ensure
    # it's properly configured with the updated routes

    app.logger.info("All blueprints registered successfully")
