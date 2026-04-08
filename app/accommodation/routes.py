# app/accommodation/routes.py
from flask import render_template
from app.accommodation import accommodation_bp

@accommodation_bp.route("/", endpoint="home")
def home():
    return render_template("accommodation_home.html")

@accommodation_bp.route("/detail/<int:id>", endpoint="detail")
def detail(id):
    return render_template("accommodation_detail.html", id=id)

""""
from flask import render_template, abort
from app.accommodation import accommodation_bp

def _service():
    try:
        from app.accommodation import services as svc
    except Exception:
        svc = None
    return svc

@accommodation_bp.route("/", endpoint="home")
def home():
    svc = _service()
    hotels = svc.list_hotels() if svc and hasattr(svc, "list_hotels") else []
    return render_template("accommodation_home.html", hotels=hotels)

@accommodation_bp.route("/<hotel_id>", endpoint="detail")
def detail(hotel_id):
    svc = _service()
    hotel = svc.get_hotel(hotel_id) if svc and hasattr(svc, "get_hotel") else None
    if hotel is None:
        abort(404)
    return render_template("accommodation_detail.html", hotel=hotel)
"""
