"""
Transport API utilities - Safe resource registration
"""
import logging
from functools import wraps

def safe_register_resource(api, resource, path, endpoint=None):
    """Safely register a Flask-RESTful resource"""
    if endpoint:
        endpoint_name = f"transport_api.{endpoint}"
        if hasattr(api, 'app') and api.app and endpoint_name in api.app.view_functions:
            logging.warning(f"Skipping duplicate endpoint: {endpoint}")
            return False
    api.add_resource(resource, path, endpoint=endpoint)
    return True