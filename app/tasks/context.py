"""Shared Flask application-context support for Celery tasks.

Celery workers are started with `celery -A app.celery_app`, outside a
Flask request. Tasks that use Flask-SQLAlchemy, current_app, or other Flask
extensions must therefore establish an application context themselves.

The factory is lazy and cached once per worker process. Importing this module
does not import or construct the Flask application, avoiding an app/Celery
import cycle during worker startup.
"""

from functools import lru_cache, wraps

from flask import has_app_context


@lru_cache(maxsize=1)
def _get_task_flask_app():
    """Construct the worker's Flask app only when its first task needs one."""
    from app import create_app

    return create_app()


def with_flask_app_context(task_fn):
    """Run a task inside a Flask app context, reusing one if already active."""
    @wraps(task_fn)
    def _wrapped(*args, **kwargs):
        if has_app_context():
            return task_fn(*args, **kwargs)

        app = _get_task_flask_app()
        with app.app_context():
            return task_fn(*args, **kwargs)

    return _wrapped
