
# app/routes.py

from flask import Blueprint, render_template
from config import APP_NAME


main_routes = Blueprint('main_routes', __name__)

@main_routes.route("/")
def home():
    return render_template("base.html", app_name=APP_NAME)
