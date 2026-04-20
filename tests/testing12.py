from app import create_app
app = create_app()
with app.app_context():
    # Test 1: Humanize Check
    try:
        from flask_humanize import Humanize
        print("✅ Flask-Humanize is active.")
    except ImportError:
        print("❌ Flask-Humanize missing.")

    # Test 2: Audit Timeline Check
    from app.audit.forensic_audit import ForensicAuditService
    timeline = ForensicAuditService.get_audit_timeline('user', '1', days=1)
    print(f"✅ Audit System Status: Found {len(timeline)} logs.")
