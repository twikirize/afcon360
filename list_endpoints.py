from app import create_app

app = create_app()

with app.app_context():
    print(f"{'Endpoint':<50} {'Methods':<20} {'Rule'}")
    print("-" * 100)
    for rule in sorted(app.url_map.iter_rules(), key=lambda x: x.endpoint):
        methods = ', '.join(sorted(rule.methods))
        print(f"{rule.endpoint:<50} {methods:<20} {rule.rule}")
