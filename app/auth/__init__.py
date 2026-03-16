# app/auth/__init__.py
"""
Auth package initialization.

Layered security principles:
- Auth handles identity, credentials, tokens, sessions, and authorization policy.
- Infra concerns (HTTPS, WAF, IP reputation, CAPTCHA, logging sinks) are NOT implemented here.
- Auth exposes hooks/signals only, for other layers to act upon.

Routes are thin; services orchestrate flows; models encapsulate state transitions.
"""
