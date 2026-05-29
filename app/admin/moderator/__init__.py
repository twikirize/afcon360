# app/admin/moderator/__init__.py
"""
Moderator module - content moderation and queue management
"""
from flask import Blueprint

# Create the moderator blueprint
moderator_bp = Blueprint('moderator', __name__, url_prefix='/moderator')

# Import routes to populate the blueprint
from app.admin.moderator import routes

__all__ = ['moderator_bp']
