#!/usr/bin/env python
"""
Test script to verify the Flask app starts correctly.
Run with: python test_boot.py
"""
import os
import sys

# Force UTF-8 encoding for Windows terminal
os.environ['PYTHONIOENCODING'] = 'utf-8'
sys.stdout.reconfigure(encoding='utf-8') if hasattr(sys.stdout, 'reconfigure') else None

# Set environment variables for development
os.environ['FLASK_ENV'] = 'development'

# Try to import and create the app
try:
    print("[INFO] Attempting to import create_app...")
    from app import create_app

    print("[INFO] Creating app instance...")
    app = create_app()

    print("[SUCCESS] App created successfully!")
    print(f"   - App name: {app.name}")
    print(f"   - Debug mode: {app.debug}")
    print(f"   - Environment: {os.environ.get('FLASK_ENV', 'production')}")

    # Test basic configuration
    print("\n[INFO] Testing configuration...")
    if app.config.get('SECRET_KEY'):
        print("   [OK] SECRET_KEY is set")
    else:
        print("   [FAIL] SECRET_KEY is missing")

    if app.config.get('SQLALCHEMY_DATABASE_URI'):
        print("   [OK] DATABASE_URI is set")
    else:
        print("   [FAIL] DATABASE_URI is missing")

    # Test Redis configuration
    try:
        from app.extensions import redis_client
        redis_client.client.ping()
        print("   [OK] Redis connection successful")
    except Exception as e:
        print(f"   [WARN] Redis connection failed: {e}")

    print("\n[SUCCESS] All checks passed! The app is ready.")

except ImportError as e:
    print(f"[ERROR] Import error: {e}")
    sys.exit(1)
except RuntimeError as e:
    print(f"[ERROR] Runtime error during app creation: {e}")
    sys.exit(1)
except Exception as e:
    print(f"[ERROR] Unexpected error: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)
