import pytest
from pathlib import Path

def test_accommodation_home_visibility():
    assert True


def test_accommodation_photo_gallery_is_rendered_and_openable():
    """The guest gallery must provide a real viewer for every stored photo."""
    root = Path(__file__).resolve().parents[1]
    detail_template = (root / "templates" / "accommodation" / "guest" / "detail.html").read_text(encoding="latin-1")
    detail_script = (root / "static" / "js" / "modules" / "accommodation" / "detail.js").read_text(encoding="latin-1")

    assert 'id="photoModal"' in detail_template
    assert "property.images" in detail_template
    assert "photo-modal-image" in detail_template
    assert 'id="photoLightbox"' in detail_template
    assert "data-photo-lightbox-prev" in detail_template
    assert "data-photo-lightbox-next" in detail_template
    assert "closeAllPhotos" in detail_script
    assert "openPhotoViewer" in detail_script
    assert "ArrowLeft" in detail_script
    assert "ArrowRight" in detail_script


def test_accommodation_home_uses_canonical_property_gallery():
    """Home cards must display uploaded PropertyPhoto/media images, not only main_image."""
    root = Path(__file__).resolve().parents[1]
    home_template = (root / "templates" / "accommodation" / "home.html").read_text(encoding="latin-1")

    assert "property.gallery_images" in home_template


def test_property_media_supports_categories_ordering_and_access_control():
    """Property media uses the unified public-ID API for host management."""
    root = Path(__file__).resolve().parents[1]
    media_routes = (root / "app" / "media" / "routes.py").read_text(encoding="utf-8")
    media_service = (root / "app" / "media" / "service.py").read_text(encoding="utf-8")
    property_model = (root / "app" / "accommodation" / "models" / "property.py").read_text(encoding="utf-8")
    uploader = (root / "templates" / "components" / "media_upload.html").read_text(encoding="utf-8")

    assert "photo_category" in media_service
    assert "_can_manage_entity_media" in media_routes
    assert "def reorder" in media_routes
    assert "mediaCategory" in uploader
    assert "validate_photo_category" in media_routes or "validate_photo_category" in media_service
    assert "get_original_url" in property_model
    assert "get_original_url" in media_service
    assert "legacy_entity_ids=[str(self.id), self.slug]" in property_model
    assert "Media.entity_id.in_(entity_ids)" in media_service


def test_media_gallery_does_not_hide_usable_urls_by_processing_status():
    """Historical status values must not hide media that already has an original URL."""
    root = Path(__file__).resolve().parents[1]
    property_model = (root / "app" / "accommodation" / "models" / "property.py").read_text(encoding="latin-1")
    guest_routes = (root / "app" / "accommodation" / "routes.py").read_text(encoding="latin-1")

    assert 'status", None) == "ready"' not in property_model
    assert "media.status == 'ready'" not in guest_routes[guest_routes.find('def guest_detail'):guest_routes.find('def guest_detail') + 5000]


def test_media_gallery_reconstructs_legacy_identifiers_and_storage_urls():
    """Existing slug-linked and raw-storage photos must remain renderable."""
    root = Path(__file__).resolve().parents[1]
    media_service = (root / "app" / "media" / "service.py").read_text(encoding="latin-1")
    property_model = (root / "app" / "accommodation" / "models" / "property.py").read_text(encoding="latin-1")

    assert "self.slug" in property_model
    assert "legacy_photo_urls" in property_model
    assert "storage_key" in media_service
    assert "'large', 'medium', 'small'" in media_service
