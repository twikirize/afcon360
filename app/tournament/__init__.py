# app/tournament/__init__.py
from flask import Blueprint

tournament_bp = Blueprint(
    "tournament",
    __name__,
    url_prefix="/tournament",
    template_folder="templates",
    static_folder="static"
)

# Import routes module and call its register function to attach routes to the blueprint.
from app.tournament import routes  # noqa: E402,F401
routes.register_routes(tournament_bp)