from flask import Flask

def create_app():
    app = Flask(__name__)
    from .routes import routes as routes_Blueprint
    app.register_blueprint(Blue)
    print("New App Created")

    return app
