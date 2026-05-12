#!/usr/bin/env python
"""
Manual registration script for trust settings blueprint
Run this to register the trust settings routes with the admin blueprint
"""

import sys
import os

# Add the app directory to Python path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from app import create_app
from app.admin.routes.trust_settings import trust_settings_bp

def register_trust_settings():
    """Register trust settings blueprint with admin"""
    app = create_app()
    
    with app.app_context():
        # Get the admin blueprint
        from app.admin import admin_bp
        
        # Register trust settings blueprint
        admin_bp.register_blueprint(trust_settings_bp)
        
        print("✅ Trust settings blueprint registered successfully!")
        print("📋 Available routes:")
        
        # Print registered routes
        for rule in app.url_map.iter_rules():
            if 'trust_settings' in str(rule.endpoint):
                print(f"   {rule.methods} {rule.rule}")
        
        print("\n🎯 Access the trust settings at: /admin/trust-settings")
        print("🔒 Requires: owner, super_admin, or admin role")

if __name__ == "__main__":
    register_trust_settings()
