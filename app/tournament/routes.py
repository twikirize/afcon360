# app/tournament/routes.py
from flask import render_template, current_app, abort

# Do NOT import app.tournament here to avoid circular imports.
# The blueprint is created in app/tournament/__init__.py and routes
# will be imported by that file after the blueprint exists.

def _get_service():
    try:
        from app.tournament import services as svc
    except Exception:
        svc = None
    return svc

def register_routes(bp):
    """Register routes on the provided blueprint object."""
    @bp.route("/", endpoint="home")
    def home():
        svc = _get_service()
        data = {"name": current_app.config.get("TOURNAMENT_NAME", "AFCON 2025"),
                "status": current_app.config.get("TOURNAMENT_STATUS", "live")}
        items = svc.list_items() if svc and hasattr(svc, "list_items") else []
        return render_template("tournament_home.html", tournament=data, items=items)

    @bp.route("/archive", endpoint="archive")
    def archive():
        svc = _get_service()
        archived = svc.list_archived() if svc and hasattr(svc, "list_archived") else []
        return render_template("tournament_archive.html", archived=archived)