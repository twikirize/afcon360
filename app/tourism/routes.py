# app/tourism/routes.py

from flask import render_template
from app.tourism import tourism_bp

# Attach routes to the tourism blueprint
@tourism_bp.route("/", endpoint="home")
def home():
    return render_template("tourism_home.html")

@tourism_bp.route("/detail/<slug>", endpoint="detail")
def detail(slug):
    return render_template("tourism_detail.html", slug=slug)


#version 3
"""
# app/tourism/routes.py
from flask import render_template, abort

def _get_service():
    try:
        from app.tourism import services as svc
    except Exception:
        svc = None
    return svc

def register_routes(bp):
    "s""Attach routes to the provided blueprint object (avoids circular imports).""s"

    @bp.route("/", endpoint="home")
    def home():
        svc = _get_service()
        packages = svc.list_packages() if svc and hasattr(svc, "list_packages") else []
        return render_template("tourism_home.html", packages=packages)

    @bp.route("/<package_id>", endpoint="detail")
    def detail(package_id):
        svc = _get_service()
        pkg = svc.get_package(package_id) if svc and hasattr(svc, "get_package") else None
        if pkg is None:
            abort(404)
        return render_template("tourism_detail.html", package=pkg)


#version 2

#app/tourism/routes.py
#This is a temporal  code for static tourim that calls itself instead of importing the tourism activities
from flask import Blueprint, render_template, current_app

tourism = Blueprint("tourism", __name__, url_prefix="/tourism")

# Local placeholder data until you wire the real service
def _sample_packages():
    return [
        {"package_id": "pkg1", "title": "Kampala City Tour", "price": 150, "image_url": "/static/img/kampala.jpg", "description": "A short city tour"},
        {"package_id": "pkg2", "title": "Mountain Safari", "price": 350, "image_url": "/static/img/safari.jpg", "description": "3 day safari package"},
    ]

@tourism.route("/", endpoint="index")
def index():
    packages = _sample_packages()
    return render_template("tourism_home.html", packages=packages)

@tourism.route("/<package_id>", endpoint="detail")
def detail(package_id):
    pkg = next((p for p in _sample_packages() if p["package_id"] == package_id), None)
    return render_template("tourism_detail.html", package=pkg)



#  this will later be revisted to create tourism module dynamic

from flask import Blueprint, render_template
from app.public.services import get_all_tourism, get_tourism_by_id

tourism = Blueprint("tourism", __name__, url_prefix="/tourism")

@tourism.route("/", endpoint="index")
def index():
    packages = get_all_tourism()
    return render_template("tourism_home.html", packages=packages)

@tourism.route("/<package_id>", endpoint="detail")
def detail(package_id):
    pkg = get_tourism_by_id(package_id)
    return render_template("tourism_detail.html", package=pkg)
"""