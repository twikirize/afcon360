"""
Production Console Package.

Provides real-time production log streaming for Owner/Super Admin.
"""
from app.production_console.routes import production_console_bp
from app.production_console.sockets import register_production_console_namespace
from app.production_console.streaming import init_production_console_logging, ProductionConsoleHandler, FrontendEventCapture

__all__ = [
    'production_console_bp',
    'register_production_console_namespace',
    'init_production_console_logging',
    'ProductionConsoleHandler',
    'FrontendEventCapture',
]