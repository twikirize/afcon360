"""Owner transport-routing page: authorization, rendering, persistence."""

from app.extensions import db
from app.geo.routing_settings import (
    FALLBACKS_KEY,
    PROFILE_KEY,
    PROVIDER_KEY,
)
from app.models.system_config import SystemConfig


def _restore(keys, originals):
    for key, original in originals.items():
        row = SystemConfig.query.filter_by(key=key).first()
        if original is None:
            if row is not None:
                db.session.delete(row)
        elif row is not None:
            row.value = original
    db.session.commit()


def test_owner_routing_page_renders_and_saves(admin_client, app):
    keys = (PROVIDER_KEY, FALLBACKS_KEY, PROFILE_KEY)
    with app.app_context():
        originals = {key: SystemConfig.get(key, None) for key in keys}
    try:
        response = admin_client.get('/admin/owner/transport-routing')
        assert response.status_code == 200
        assert b'Transport Routing Engine' in response.data

        response = admin_client.post(
            '/admin/owner/transport-routing',
            data={
                'provider': 'osrm',
                'fallbacks': ['geoapify', 'ors'],
                'profile': 'auto',
            },
            follow_redirects=True,
        )
        assert response.status_code == 200
        with app.app_context():
            assert SystemConfig.get(PROVIDER_KEY) == 'osrm'
            assert SystemConfig.get(FALLBACKS_KEY) == 'geoapify,ors'
            assert SystemConfig.get(PROFILE_KEY) == 'auto'
    finally:
        with app.app_context():
            _restore(keys, originals)


def test_owner_settings_links_to_routing(admin_client):
    response = admin_client.get('/admin/owner/settings')
    assert response.status_code == 200
    assert b'/admin/owner/transport-routing' in response.data


def test_transport_settings_links_owner_to_routing(admin_client):
    response = admin_client.get('/transport/settings')
    assert response.status_code == 200
    assert b'/admin/owner/transport-routing' in response.data


def test_regular_user_cannot_access_owner_routing(authenticated_client):
    response = authenticated_client.get('/admin/owner/transport-routing',
                                         follow_redirects=True)
    assert b'Transport Routing Engine' not in response.data
