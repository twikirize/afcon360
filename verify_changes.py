import sys

errors = []

with open('static/js/global/media-manager.js', 'r', encoding='utf-8', errors='replace') as f:
    js = f.read()

if 'parseInt(mediaId)' in js:
    errors.append('media-manager.js: parseInt(mediaId) still present')
if "mediaId === 'NaN'" not in js:
    errors.append('media-manager.js: NaN check missing')
if 'CSS.escape' not in js:
    errors.append('media-manager.js: CSS.escape missing')
if 'this.loadExistingMedia()' not in js:
    errors.append('media-manager.js: loadExistingMedia refresh missing')
if "alert(data.error or 'Delete failed')" in js or "alert(data.error || 'Delete failed')" in js:
    errors.append('media-manager.js: old alert still in deleteMedia')
if '(m.public_id' not in js or '!== mediaId' not in js:
    errors.append('media-manager.js: public_id filter missing in deleteMedia')
if '(m.public_id' not in js or '=== mediaId' not in js:
    errors.append('media-manager.js: public_id comparison missing in setCover')
if 'media.public_id' not in js:
    errors.append('media-manager.js: public_id in renderGallery data-id missing')

with open('app/media/routes.py', 'r', encoding='utf-8', errors='replace') as f:
    py = f.read()

if 'set-cover' not in py:
    errors.append('routes.py: set-cover route missing')
if 'Media.public_id == media_public_id' not in py:
    errors.append('routes.py: set-cover does not filter by public_id')
if "Media.is_cover = False" not in py:
    errors.append('routes.py: set-cover does not clear other covers')
if 'media.is_cover = True' not in py:
    errors.append('routes.py: set-cover does not set is_cover')

with open('app/media/service.py', 'r', encoding='utf-8', errors='replace') as f:
    svc = f.read()

if 'items = q.all()' not in svc:
    errors.append('service.py: get_for_entity does not use items variable')
if 'item.public_id = str(item.id)' not in svc:
    errors.append('service.py: get_for_entity does not ensure public_id')
if 'hasattr(item' not in svc:
    errors.append('service.py: get_for_entity does not check hasattr')

with open('templates/components/media_upload.html', 'r', encoding='utf-8', errors='replace') as f:
    html = f.read()

if 'media-item-template' not in html:
    errors.append('media_upload.html: media-item-template missing')
if 'media.public_id or media.id or media.media_id' not in html:
    errors.append('media_upload.html: public_id fallback missing')
if 'media-placeholder' not in html:
    errors.append('media_upload.html: placeholder missing')
if 'onerror' not in html:
    errors.append('media_upload.html: onerror handler missing')

if errors:
    print('ERRORS FOUND:')
    for e in errors:
        print('  FAIL:', e)
    sys.exit(1)
else:
    print('All changes verified successfully!')