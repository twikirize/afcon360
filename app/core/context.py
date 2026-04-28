# app/core/context.py
"""
Centralized request-scoped identity context.

Provides a forensically safe way to access the real actor (logged-in user)
versus the effective user (impersonated target or the actor themselves).

Usage:
    from app.core.context import RequestContext

    actor = RequestContext.get_actor()
    effective = RequestContext.get_effective_user()
"""
from __future__ import annotations

from flask import g
from typing import Optional


class RequestContext:
    @staticmethod
    def set_actor(user) -> None:
        """Set the real actor (the authenticated user making the request)."""
        g.actor_user = user

    @staticmethod
    def set_effective_user(user) -> None:
        """Set the effective user (impersonated user or actor if not impersonating)."""
        g.effective_user = user

    @staticmethod
    def get_actor():
        """Return the real actor for the current request, if any."""
        return getattr(g, "actor_user", None)

    @staticmethod
    def get_effective_user():
        """Return the effective user for the current request, if any."""
        return getattr(g, "effective_user", None)
