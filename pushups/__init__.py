from flask import Flask

def create_app():
    app = Flask(__name__)
    # Register blueprints
    try:
        from .routes import routes as routes_blueprint
        app.register_blueprint(routes_blueprint)
    except ImportError:
        pass
    print("New App Created")
    return app
