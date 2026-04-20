# check_blueprints.py
import sys
sys.path.insert(0, '.')

from flask import Flask
from app import create_app

app = create_app()

print("\n" + "="*60)
print("REGISTERED BLUEPRINTS:")
print("="*60)
for bp_name, bp in app.blueprints.items():
    print(f"  • {bp_name} -> {bp.url_prefix}")

print("\n" + "="*60)
print("ADMIN SUB-BLUEPRINTS:")
print("="*60)
from app.admin import admin_bp
if hasattr(admin_bp, 'blueprints'):
    for bp_name, bp in admin_bp.blueprints.items():
        print(f"  • {bp_name} -> {bp.url_prefix}")
else:
    print("  No sub-blueprints found")

print("\n" + "="*60)
print("ALL ENDPOINTS (moderator related):")
print("="*60)
for endpoint in app.view_functions.keys():
    if 'moderator' in endpoint:
        print(f"  • {endpoint}")
