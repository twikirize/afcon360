from sqlalchemy import select

from app import create_app
from app.config import TestingConfig
from app.identity.models.organisation import Organisation
from app.identity.models.user import User
from app.identity.models.organisation_member import OrganisationMember


app = create_app(config_object=TestingConfig)
with app.app_context():
    rows = app.extensions['sqlalchemy'].session.execute(
        select(User.username, Organisation.legal_name, OrganisationMember.job_title)
        .join(OrganisationMember, OrganisationMember.user_id == User.id)
        .join(Organisation, Organisation.id == OrganisationMember.organisation_id)
        .limit(10)
    ).all()
    for username, org_name, role in rows:
        print(f"User: {username}, Organisation: {org_name}, Job title: {role}")
