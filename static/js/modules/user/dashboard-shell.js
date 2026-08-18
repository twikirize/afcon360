/**
 * AFCON360 shared dashboard shell controller.
 * Pane navigation and operating-context selection live here so the shell
 * remains CSP-safe and all context mutations carry the server CSRF token.
 */
(function () {
    const shellContent = document.getElementById('shellContent');
    const leftPanel = document.getElementById('leftPanel');
    const mobileOverlay = document.getElementById('mobileOverlay');
    const navItems = document.querySelectorAll('.nav-item');
    const initialSectionsHtml = shellContent ? shellContent.innerHTML : '';
    let contentSections = document.querySelectorAll('.content-section');
    let currentPaneUrl = null;
    let paneRequestId = 0;

    function toggleMobileNav() {
        if (!leftPanel || !mobileOverlay) return;
        leftPanel.classList.toggle('open');
        mobileOverlay.classList.toggle('active');
    }

    function setActiveNav(selector, value) {
        navItems.forEach(function (item) { item.classList.remove('active'); });
        const match = document.querySelector('.nav-item[' + selector + '="' + value + '"]');
        if (match) match.classList.add('active');
    }

    function runInlineScripts(root) {
        root.querySelectorAll('script').forEach(function (oldScript) {
            const script = document.createElement('script');
            if (oldScript.src) script.src = oldScript.src;
            script.textContent = oldScript.textContent;
            oldScript.parentNode.replaceChild(script, oldScript);
        });
    }

    function restoreInlineSections() {
        if (!shellContent || (!currentPaneUrl && shellContent.innerHTML.trim() === initialSectionsHtml.trim())) {
            return;
        }
        shellContent.innerHTML = initialSectionsHtml;
        currentPaneUrl = null;
        contentSections = document.querySelectorAll('.content-section');
        runInlineScripts(shellContent);
    }

    function showSection(id) {
        if (!shellContent) return;
        restoreInlineSections();
        setActiveNav('data-section', id);
        contentSections.forEach(function (section) { section.classList.remove('active'); });
        const target = document.getElementById(id);
        if (target) target.classList.add('active');

        const url = new URL(window.location.href);
        url.searchParams.delete('view');
        url.hash = id;
        history.replaceState({ section: id }, '', url.toString());
        if (leftPanel && leftPanel.classList.contains('open')) toggleMobileNav();
    }

    function loadPane(paneUrl) {
        if (!shellContent || !paneUrl) return;
        setActiveNav('data-pane-url', paneUrl);
        restoreInlineSections();
        contentSections.forEach(function (section) { section.classList.remove('active'); });
        const requestId = ++paneRequestId;
        shellContent.innerHTML = '<div class="pane-loading"><div class="pane-spinner"></div><p>Establishing secure connection...</p></div>';

        const separator = paneUrl.indexOf('?') >= 0 ? '&' : '?';
        fetch(paneUrl + separator + '_pane=1', {
            credentials: 'same-origin',
            headers: { 'X-Requested-With': 'XMLHttpRequest' }
        })
            .then(function (response) {
                if (response.status === 401) {
                    window.location.href = '/auth/login';
                    return null;
                }
                if (!response.ok) throw new Error('HTTP ' + response.status);
                return response.text();
            })
            .then(function (html) {
                if (requestId !== paneRequestId || !html) return;
                shellContent.innerHTML = html;
                currentPaneUrl = paneUrl;
                runInlineScripts(shellContent);
                const url = new URL(window.location.href);
                url.searchParams.set('view', paneUrl);
                url.hash = '';
                history.pushState({ pane: paneUrl }, '', url.toString());
            })
            .catch(function (error) {
                if (requestId !== paneRequestId) return;
                currentPaneUrl = paneUrl;
                shellContent.innerHTML = '<div class="pane-loading pane-error"><i class="fas fa-exclamation-circle"></i><p>' + error.message + '</p><button class="btn-retry" type="button" data-action="retry-pane">Retry Connection</button></div>';
            });

        if (leftPanel && leftPanel.classList.contains('open')) toggleMobileNav();
    }

    function switchContext(option) {
        const switcher = document.querySelector('[data-context-switcher]');
        if (!switcher || !option) return;
        const payload = {
            type: option.dataset.contextType,
            id: option.dataset.contextId || null,
            role: option.dataset.contextRole || null,
            next: window.location.pathname + window.location.search
        };
        option.disabled = true;
        console.info('[AFCON360] Switching operating context', {
            type: payload.type,
            id: payload.id,
            role: payload.role
        });
        fetch(switcher.dataset.switchUrl, {
            method: 'POST',
            credentials: 'same-origin',
            headers: {
                'Content-Type': 'application/json',
                'Accept': 'application/json',
                'X-CSRFToken': switcher.dataset.csrfToken,
                'X-Requested-With': 'XMLHttpRequest'
            },
            body: JSON.stringify(payload)
        })
            .then(function (response) {
                return response.json().then(function (body) {
                    if (!response.ok || !body.success) throw new Error(body.error || 'Context switch failed');
                    return body;
                });
            })
            .then(function (body) {
                const target = body.redirect || '/user/dashboard';
                console.info('[AFCON360] Operating context switched', {
                    type: body.context && body.context.type,
                    id: body.context && body.context.public_id,
                    role: body.context && body.context.role,
                    redirect: target
                });
                window.location.assign(target);
            })
            .catch(function (error) {
                option.disabled = false;
                console.error('[AFCON360] Operating context switch failed', error);
                window.dispatchEvent(new CustomEvent('afcon-context-error', { detail: { message: error.message } }));
            });
    }

    document.addEventListener('click', function (event) {
        const actionButton = event.target.closest('[data-action]');
        if (actionButton) {
            if (actionButton.dataset.action === 'toggle-nav') toggleMobileNav();
            if (actionButton.dataset.action === 'retry-pane') {
                if (currentPaneUrl) loadPane(currentPaneUrl);
                else window.location.reload();
            }
        }

        const contextOption = event.target.closest('.context-option');
        if (contextOption) {
            event.preventDefault();
            switchContext(contextOption);
            return;
        }

        const navItem = event.target.closest('.nav-item');
        if (navItem) {
            event.preventDefault();
            if (navItem.dataset.section) showSection(navItem.dataset.section);
            else if (navItem.dataset.paneUrl) loadPane(navItem.dataset.paneUrl);
            return;
        }

        const paneLink = event.target.closest('[data-pane-url]');
        if (paneLink && !paneLink.classList.contains('nav-item')) {
            event.preventDefault();
            loadPane(paneLink.dataset.paneUrl);
        }
    });

    const switcherToggle = document.getElementById('switcher-toggle');
    const switcherPanel = document.getElementById('switcher-panel');
    if (switcherToggle && switcherPanel) {
        switcherToggle.addEventListener('click', function (event) {
            event.stopPropagation();
            const expanded = switcherToggle.getAttribute('aria-expanded') === 'true';
            switcherToggle.setAttribute('aria-expanded', String(!expanded));
            switcherPanel.hidden = expanded;
        });
        document.addEventListener('click', function (event) {
            if (!switcherToggle.contains(event.target) && !switcherPanel.contains(event.target)) {
                switcherPanel.hidden = true;
                switcherToggle.setAttribute('aria-expanded', 'false');
            }
        });
    }

    const params = new URLSearchParams(window.location.search);
    const viewUrl = params.get('view');
    const hash = window.location.hash.slice(1);
    if (viewUrl) loadPane(viewUrl);
    else if (hash && document.getElementById(hash)) showSection(hash);
    else showSection('dashboard');

    window.addEventListener('popstate', function () {
        const pane = new URLSearchParams(window.location.search).get('view');
        if (pane) loadPane(pane);
        else showSection(window.location.hash.slice(1) || 'dashboard');
    });
})();