"""Public-facing company, help and legal-information pages.

These pages intentionally contain editable draft copy. Legal notices are working
drafts and must be reviewed against the actual operating entity, providers and
applicable laws before being treated as final.
"""
from flask import Blueprint, render_template

public_pages_bp = Blueprint("public_pages", __name__)


@public_pages_bp.get("/about")
def about():
    return render_template("about.html")


@public_pages_bp.get("/contact")
def contact():
    return render_template("contact.html")


@public_pages_bp.get("/privacy-policy")
def privacy_policy():
    return render_template("privacy_policy.html")


@public_pages_bp.get("/data-protection")
def data_protection():
    return render_template("data_protection.html")


@public_pages_bp.get("/terms-of-service")
def terms_of_service():
    return render_template("terms_of_service.html")


@public_pages_bp.get("/refunds-and-cancellations")
def refunds_and_cancellations():
    return render_template("refunds_and_cancellations.html")


@public_pages_bp.get("/faqs")
def faqs():
    return render_template("faqs.html")


@public_pages_bp.get("/cookie-policy")
def cookie_policy():
    return render_template("cookie_policy.html")
