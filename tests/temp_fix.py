app.logger.handlers.clear()  # Remove Flask's default handler to prevent duplicate logging

# ------------------------------------------------------------------
# PERMANENT FIX: Custom Jinja2 Loader with Encoding Fallback
# Prevents UnicodeDecodeError by forcing UTF-8 with fallback encodings
# ------------------------------------------------------------------
from jinja2 import FileSystemLoader, ChoiceLoader
import warnings
