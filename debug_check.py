import sys
sys.path.insert(0, '.')
from app import create_app

app = create_app(config_object='app.config.TestingConfig')
with app.app_context():
    from app.extensions import db
    from app.identity.models import OrganisationProviderCapability
    from app.identity.models import ProviderCapabilityCode

    # Count by capability_code
    for code in ['accommodation', 'transport', 'events', 'tourism', 'venue']:
        count = db.session.query(OrganisationProviderCapability).filter_by(capability_code=code).count()
        print(f'capability_code={code}: {count} rows')

    # Show sample rows with events capability
    rows = db.session.query(OrganisationProviderCapability).filter_by(capability_code='events').limit(5).all()
    print('\nSample events rows:')
    for r in rows:
        print(f'  org_id={r.organisation_id}, cap_code={r.capability_code}, status={r.status}, is_deleted={r.is_deleted}')

    total_events = db.session.query(OrganisationProviderCapability).filter_by(capability_code='events').count()
    print(f'\nTotal events rows: {total_events}')

    # Check alembic version
    result = db.session.execute(db.text('SELECT version_num FROM alembic_version')).scalar()
    print(f'\nCurrent alembic version: {result}')