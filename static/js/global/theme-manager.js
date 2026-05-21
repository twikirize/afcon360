/**
 * AFCON 360 Theme Manager
 * Handles user preferences, live preview, and theme switching
 * Version: 2.0.0 - Manual save with live preview
 */

class ThemeManager {
    constructor() {
        // Working copy (changes apply immediately to preview)
        this.workingPreferences = null;
        // Saved copy (last saved to server)
        this.savedPreferences = null;
        this.initialized = false;
        this.init();
    }

    async init() {
        // Check if theme manager should be disabled on this page
        if (document.documentElement.hasAttribute('data-theme-disabled')) {
            console.log('Theme Manager disabled on this page');
            return;
        }

        try {
            // Load user preferences
            await this.loadUserPreferences();

            // Apply preferences
            this.applyPreferences();

            // Setup event listeners
            this.setupEventListeners();

            // Listen for system dark mode changes
            this.setupSystemDarkModeListener();

            // Apply dashboard colors and setup dashboard listeners
            this.applyDashboardColors();
            this.setupDashboardEventListeners();
            this.syncUIControls();

            this.initialized = true;
            console.log('Theme Manager initialized with manual save mode');
        } catch (error) {
            console.error('Theme Manager initialization failed:', error);
        }
    }

    async loadUserPreferences() {
        try {
            const response = await fetch('/theme/api/preferences', {
                headers: {
                    'Cache-Control': 'no-cache',
                    'Pragma': 'no-cache'
                },
                credentials: 'same-origin',
                redirect: 'error'
            });

            // Check if response is a redirect (3xx status)
            if (response.redirected) {
                console.warn('Theme API attempted redirect, using defaults');
                this.savedPreferences = this.getDefaultPreferences();
                this.workingPreferences = JSON.parse(JSON.stringify(this.savedPreferences));
                return;
            }

            if (response.ok) {
                const contentType = response.headers.get('content-type');
                if (contentType && contentType.includes('application/json')) {
                    const data = await response.json();
                    this.savedPreferences = data || this.getDefaultPreferences();
                } else {
                    console.warn('Theme API returned non-JSON response, using defaults');
                    this.savedPreferences = this.getDefaultPreferences();
                }
            } else if (response.status === 401 || response.status === 403) {
                // User is not authenticated or lacks permission - use defaults
                console.log('User not authenticated for theme preferences, using defaults');
                this.savedPreferences = this.getDefaultPreferences();
            } else {
                console.warn(`Theme API returned status ${response.status}, using defaults`);
                this.savedPreferences = this.getDefaultPreferences();
            }
        } catch (e) {
            console.warn('Could not load preferences, using defaults:', e);
            this.savedPreferences = this.getDefaultPreferences();
        }

        // Initialize working preferences as a copy of saved preferences
        if (!this.workingPreferences) {
            this.workingPreferences = JSON.parse(JSON.stringify(this.savedPreferences || this.getDefaultPreferences()));
        }
    }

    isUserAuthenticated() {
        // Check meta tag for authentication status
        const meta = document.querySelector('meta[name="user-authenticated"]');
        if (meta) {
            return meta.getAttribute('content') === 'true';
        }
        // Fallback: check for user data in window object
        if (window.currentUser && window.currentUser.isAuthenticated) {
            return true;
        }
        return false;
    }

    getDefaultPreferences() {
        return {
            font_scale: 1.0,
            high_contrast: 'off',
            dyslexic_font: false,
            color_blind_mode: 'none',
            dark_mode: 'system',
            reduced_motion: false,
            reading_width: 'full',
            compact_mode: false,
            custom_accent: null,
            // Dashboard colors
            dashboard_page_bg: '#f5f7fa',
            dashboard_sidebar_bg: '#ffffff',
            dashboard_card_bg: '#ffffff',
            dashboard_header_bg: '#1a1a2e',
            dashboard_primary: '#10b981',
            dashboard_text_primary: '#111827',
            dashboard_border_radius: 8,
            dashboard_card_padding: 16
        };
    }

    applyPreferences() {
        if (!this.workingPreferences) return;

        // Apply font scale
        document.documentElement.style.setProperty('--user-font-scale', this.workingPreferences.font_scale);

        // Apply font family for dyslexia
        if (this.workingPreferences.dyslexic_font) {
            document.body.classList.add('dyslexic-font');
        } else {
            document.body.classList.remove('dyslexic-font');
        }

        // Apply high contrast mode
        this.applyHighContrast(this.workingPreferences.high_contrast);

        // Apply color blindness filter
        this.applyColorBlindMode(this.workingPreferences.color_blind_mode);

        // Apply dark/light mode
        this.applyDarkMode(this.workingPreferences.dark_mode);

        // Apply reduced motion
        if (this.workingPreferences.reduced_motion) {
            document.body.classList.add('reduced-motion');
        } else {
            document.body.classList.remove('reduced-motion');
        }

        // Apply reading width
        this.applyReadingWidth(this.workingPreferences.reading_width);

        // Apply compact mode
        if (this.workingPreferences.compact_mode) {
            document.body.classList.add('compact-mode');
        } else {
            document.body.classList.remove('compact-mode');
        }

        // Apply custom accent color
        if (this.workingPreferences.custom_accent) {
            document.documentElement.style.setProperty('--brand-primary', this.workingPreferences.custom_accent);
            const rgb = this.hexToRgb(this.workingPreferences.custom_accent);
            document.documentElement.style.setProperty('--brand-primary-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`);
        } else {
            // Reset to default (will be overridden by global CSS)
            document.documentElement.style.removeProperty('--brand-primary');
            document.documentElement.style.removeProperty('--brand-primary-rgb');
        }

        // Apply dashboard colors
        this.applyDashboardColors();
    }

    applyHighContrast(mode) {
        // Remove existing contrast classes
        document.body.classList.remove('contrast-yellow-black', 'contrast-white-black');

        switch(mode) {
            case 'yellow_black':
                document.body.classList.add('contrast-yellow-black');
                break;
            case 'white_black':
                document.body.classList.add('contrast-white-black');
                break;
            default:
                // No contrast class
                break;
        }
    }

    applyColorBlindMode(mode) {
        // Remove existing filter classes
        document.body.classList.remove('protanopia', 'deuteranopia', 'tritanopia', 'monochromacy');

        if (mode !== 'none') {
            document.body.classList.add(mode);
        }
    }

    applyDarkMode(mode) {
        // Remove existing mode classes
        document.body.classList.remove('dark-mode', 'light-mode');

        switch(mode) {
            case 'dark':
                document.body.classList.add('dark-mode');
                break;
            case 'light':
                document.body.classList.add('light-mode');
                break;
            case 'system':
                // Check system preference
                if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
                    document.body.classList.add('dark-mode');
                } else {
                    document.body.classList.add('light-mode');
                }
                break;
            default:
                break;
        }
    }

    applyReadingWidth(width) {
        document.body.classList.remove('reading-width-narrow', 'reading-width-medium', 'reading-width-full');

        if (width !== 'full') {
            document.body.classList.add(`reading-width-${width}`);
        }
    }

    async saveUserPreferences() {
        const saveBtn = document.getElementById('saveDashboardPreferences');
        const originalText = saveBtn ? saveBtn.innerHTML : 'Save';

        if (saveBtn) {
            saveBtn.disabled = true;
            saveBtn.innerHTML = '<i class="fas fa-spinner fa-spin"></i> Saving...';
        }

        try {
            const response = await fetch('/theme/preferences/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify(this.workingPreferences),
                credentials: 'same-origin',
                redirect: 'error'
            });

            // Check for redirect
            if (response.redirected) {
                console.error('Save endpoint attempted redirect');
                this.showToast('Failed to save preferences (redirect)', 'error');
                return;
            }

            if (response.ok) {
                // Save successful - update savedPreferences
                this.savedPreferences = JSON.parse(JSON.stringify(this.workingPreferences));
                this.showToast('Preferences saved successfully!', 'success');

                // Reload the user CSS to apply changes
                const userCssLink = document.getElementById('user-theme-css');
                if (userCssLink) {
                    const newHref = userCssLink.href.split('?')[0] + '?t=' + Date.now();
                    userCssLink.href = newHref;
                }
            } else if (response.status === 401 || response.status === 403) {
                console.error('User not authenticated to save preferences');
                this.showToast('Not authenticated to save preferences', 'error');
            } else {
                console.error('Failed to save preference:', response.status);
                this.showToast('Failed to save preferences', 'error');
            }
        } catch (error) {
            console.error('Error saving preference:', error);
            this.showToast('Network error saving preferences', 'error');
        } finally {
            if (saveBtn) {
                saveBtn.disabled = false;
                saveBtn.innerHTML = originalText;
            }
        }
    }

    resetToSaved() {
        if (!this.savedPreferences) return;

        // Revert workingPreferences to savedPreferences
        this.workingPreferences = JSON.parse(JSON.stringify(this.savedPreferences));

        // Update UI and apply all preferences
        this.syncUIControls();
        this.updatePreviewControls();
        this.applyPreferences();
        this.showToast('Reverted to last saved preferences', 'info');
    }

    async resetToDefaults() {
        this.workingPreferences = this.getDefaultPreferences();
        this.applyPreferences();
        this.syncUIControls();
        this.updatePreviewControls();

        // Only reset on server if authenticated
        if (!this.isUserAuthenticated()) {
            this.showToast('Preferences reset locally (guest mode)', 'info');
            return;
        }

        try {
            const response = await fetch('/theme/reset', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                credentials: 'same-origin',
                redirect: 'error'
            });

            // Check for redirect
            if (response.redirected) {
                console.error('Reset endpoint attempted redirect');
                this.showToast('Failed to reset preferences (redirect)', 'error');
                return;
            }

            if (response.ok) {
                this.savedPreferences = JSON.parse(JSON.stringify(this.workingPreferences));
                this.showToast('Preferences reset to defaults', 'success');
            } else if (response.status === 401 || response.status === 403) {
                console.error('User not authenticated to reset preferences');
                this.showToast('Not authenticated to reset preferences', 'error');
            } else {
                console.error('Error resetting preferences:', response.status);
                this.showToast('Failed to reset preferences', 'error');
            }
        } catch (error) {
            console.error('Error resetting preferences:', error);
            this.showToast('Network error resetting preferences', 'error');
        }
    }

    setupEventListeners() {
        // Font size slider
        const fontSizeSlider = document.getElementById('fontSizeSlider');
        const fontSizeValue = document.getElementById('fontSizeValue');
        if (fontSizeSlider && this.workingPreferences) {
            fontSizeSlider.value = this.workingPreferences.font_scale;
            fontSizeSlider.addEventListener('input', (e) => {
                const value = parseFloat(e.target.value);
                if (fontSizeValue) fontSizeValue.textContent = value.toFixed(1) + 'x';
                this.workingPreferences.font_scale = value;
                this.applyPreferences(); // Live preview
            });
        }

        // Dyslexic font toggle
        const dyslexicToggle = document.getElementById('dyslexicFont');
        if (dyslexicToggle && this.workingPreferences) {
            dyslexicToggle.checked = this.workingPreferences.dyslexic_font;
            dyslexicToggle.addEventListener('change', (e) => {
                this.workingPreferences.dyslexic_font = e.target.checked;
                this.applyPreferences(); // Live preview
            });
        }

        // High contrast radios
        const contrastRadios = document.querySelectorAll('input[name="highContrast"]');
        contrastRadios.forEach(radio => {
            if (this.workingPreferences && radio.value === this.workingPreferences.high_contrast) {
                radio.checked = true;
            }
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.workingPreferences.high_contrast = e.target.value;
                    this.applyPreferences(); // Live preview
                }
            });
        });

        // Color blind mode select
        const colorBlindSelect = document.getElementById('colorBlindMode');
        if (colorBlindSelect && this.workingPreferences) {
            colorBlindSelect.value = this.workingPreferences.color_blind_mode;
            colorBlindSelect.addEventListener('change', (e) => {
                this.workingPreferences.color_blind_mode = e.target.value;
                this.applyPreferences(); // Live preview
            });
        }

        // Dark mode radios
        const darkModeRadios = document.querySelectorAll('input[name="darkMode"]');
        darkModeRadios.forEach(radio => {
            if (this.workingPreferences && radio.value === this.workingPreferences.dark_mode) {
                radio.checked = true;
            }
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.workingPreferences.dark_mode = e.target.value;
                    this.applyPreferences(); // Live preview
                }
            });
        });

        // Reduced motion toggle
        const reducedMotionToggle = document.getElementById('reducedMotion');
        if (reducedMotionToggle && this.workingPreferences) {
            reducedMotionToggle.checked = this.workingPreferences.reduced_motion;
            reducedMotionToggle.addEventListener('change', (e) => {
                this.workingPreferences.reduced_motion = e.target.checked;
                this.applyPreferences(); // Live preview
            });
        }

        // Reading width radios
        const widthRadios = document.querySelectorAll('input[name="readingWidth"]');
        widthRadios.forEach(radio => {
            if (this.workingPreferences && radio.value === this.workingPreferences.reading_width) {
                radio.checked = true;
            }
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.workingPreferences.reading_width = e.target.value;
                    this.applyPreferences(); // Live preview
                }
            });
        });

        // Compact mode toggle
        const compactToggle = document.getElementById('compactMode');
        if (compactToggle && this.workingPreferences) {
            compactToggle.checked = this.workingPreferences.compact_mode;
            compactToggle.addEventListener('change', (e) => {
                this.workingPreferences.compact_mode = e.target.checked;
                this.applyPreferences(); // Live preview
            });
        }

        // Custom accent color
        const accentPicker = document.getElementById('customAccent');
        if (accentPicker && this.workingPreferences) {
            accentPicker.value = this.workingPreferences.custom_accent || '#2d5a2d';
            accentPicker.addEventListener('change', (e) => {
                this.workingPreferences.custom_accent = e.target.value;
                this.applyPreferences(); // Live preview
            });
        }

        // Reset button
        const resetBtn = document.getElementById('resetPreferences');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                if (confirm('Reset all preferences to default values?')) {
                    this.resetToDefaults();
                }
            });
        }
    }

    updatePreviewControls() {
        // Update all form controls to match current preferences
        if (!this.workingPreferences) return;

        const fontSizeSlider = document.getElementById('fontSizeSlider');
        if (fontSizeSlider) fontSizeSlider.value = this.workingPreferences.font_scale;

        const dyslexicToggle = document.getElementById('dyslexicFont');
        if (dyslexicToggle) dyslexicToggle.checked = this.workingPreferences.dyslexic_font;

        const reducedMotionToggle = document.getElementById('reducedMotion');
        if (reducedMotionToggle) reducedMotionToggle.checked = this.workingPreferences.reduced_motion;

        const compactToggle = document.getElementById('compactMode');
        if (compactToggle) compactToggle.checked = this.workingPreferences.compact_mode;

        const colorBlindSelect = document.getElementById('colorBlindMode');
        if (colorBlindSelect) colorBlindSelect.value = this.workingPreferences.color_blind_mode;

        const accentPicker = document.getElementById('customAccent');
        if (accentPicker) accentPicker.value = this.workingPreferences.custom_accent || '#2d5a2d';
    }

    setupSystemDarkModeListener() {
        if (window.matchMedia) {
            const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
            darkModeQuery.addEventListener('change', (e) => {
                if (this.workingPreferences && this.workingPreferences.dark_mode === 'system') {
                    this.applyDarkMode('system');
                }
            });
        }
    }

    getCsrfToken() {
        const meta = document.querySelector('meta[name="csrf-token"]');
        return meta ? meta.getAttribute('content') : '';
    }

    hexToRgb(hex) {
        if (!hex) return { r: 45, g: 90, b: 45 };

        // Remove the # if present
        hex = hex.replace(/^#/, '');

        // Handle 3-digit hex
        if (hex.length === 3) {
            hex = hex[0] + hex[0] + hex[1] + hex[1] + hex[2] + hex[2];
        }

        // Validate hex length
        if (hex.length !== 6) {
            return { r: 45, g: 90, b: 45 };
        }

        const result = /^([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 45, g: 90, b: 45 };
    }

    showToast(message, type = 'info') {
        // Check if there's already a toast system in place
        // If Bootstrap toasts are available, use them instead
        if (typeof bootstrap !== 'undefined' && bootstrap.Toast) {
            // Create a Bootstrap toast
            const toastEl = document.createElement('div');
            toastEl.className = `toast align-items-center text-bg-${type === 'success' ? 'success' : type === 'error' ? 'danger' : 'info'} border-0`;
            toastEl.setAttribute('role', 'alert');
            toastEl.setAttribute('aria-live', 'assertive');
            toastEl.setAttribute('aria-atomic', 'true');

            toastEl.innerHTML = `
                <div class="d-flex">
                    <div class="toast-body">
                        ${message}
                    </div>
                    <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast"></button>
                </div>
            `;

            const container = document.getElementById('toast-container') || (() => {
                const div = document.createElement('div');
                div.id = 'toast-container';
                div.className = 'toast-container position-fixed bottom-0 end-0 p-3';
                div.style.zIndex = '9999';
                document.body.appendChild(div);
                return div;
            })();

            container.appendChild(toastEl);
            const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
            toast.show();

            // Remove element after hide
            toastEl.addEventListener('hidden.bs.toast', () => {
                toastEl.remove();
            });
        } else {
            // Fallback to custom toast
            let toastContainer = document.getElementById('toast-container');
            if (!toastContainer) {
                toastContainer = document.createElement('div');
                toastContainer.id = 'toast-container';
                toastContainer.style.cssText = `
                    position: fixed;
                    bottom: 20px;
                    right: 20px;
                    z-index: 9999;
                `;
                document.body.appendChild(toastContainer);
            }

            const toast = document.createElement('div');
            toast.className = `toast-notification ${type}`;
            toast.style.cssText = `
                background: ${type === 'success' ? '#2d5a2d' : type === 'error' ? '#dc3545' : '#17a2b8'};
                color: white;
                padding: 12px 20px;
                border-radius: 8px;
                margin-top: 10px;
                font-size: 14px;
                animation: slideIn 0.3s ease;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
            `;
            toast.textContent = message;

            toastContainer.appendChild(toast);

            setTimeout(() => {
                toast.style.animation = 'slideOut 0.3s ease';
                setTimeout(() => toast.remove(), 300);
            }, 3000);
        }
    }

    applyDashboardColors() {
        if (!this.workingPreferences) return;

        if (this.workingPreferences.dashboard_page_bg) {
            document.documentElement.style.setProperty('--bg-page', this.workingPreferences.dashboard_page_bg);
        }
        if (this.workingPreferences.dashboard_sidebar_bg) {
            document.documentElement.style.setProperty('--bg-sidebar', this.workingPreferences.dashboard_sidebar_bg);
        }
        if (this.workingPreferences.dashboard_card_bg) {
            document.documentElement.style.setProperty('--bg-card', this.workingPreferences.dashboard_card_bg);
        }
        if (this.workingPreferences.dashboard_header_bg) {
            document.documentElement.style.setProperty('--bg-header', this.workingPreferences.dashboard_header_bg);
        }
        if (this.workingPreferences.dashboard_primary) {
            document.documentElement.style.setProperty('--green-500', this.workingPreferences.dashboard_primary);
        }
        if (this.workingPreferences.dashboard_text_primary) {
            document.documentElement.style.setProperty('--text-primary', this.workingPreferences.dashboard_text_primary);
        }
        if (this.workingPreferences.dashboard_border_radius) {
            const r = this.workingPreferences.dashboard_border_radius;
            document.documentElement.style.setProperty('--radius-sm', (r * 0.75) + 'px');
            document.documentElement.style.setProperty('--radius-md', r + 'px');
            document.documentElement.style.setProperty('--radius-lg', (r * 1.5) + 'px');
        }
        if (this.workingPreferences.dashboard_card_padding) {
            document.documentElement.style.setProperty('--spacing-lg', this.workingPreferences.dashboard_card_padding + 'px');
        }
    }

    syncUIControls() {
        if (!this.workingPreferences) return;

        // Update all color pickers from workingPreferences
        const colorMappings = {
            dashboard_page_bg: 'dashboardPageBg',
            dashboard_sidebar_bg: 'dashboardSidebarBg',
            dashboard_card_bg: 'dashboardCardBg',
            dashboard_header_bg: 'dashboardHeaderBg',
            dashboard_primary: 'dashboardPrimaryGreen',
            dashboard_text_primary: 'dashboardTextPrimary'
        };

        for (const [prefKey, elementId] of Object.entries(colorMappings)) {
            const colorPicker = document.getElementById(elementId);
            const textInput = document.getElementById(elementId + 'Text');
            if (colorPicker && this.workingPreferences[prefKey]) {
                colorPicker.value = this.workingPreferences[prefKey];
                if (textInput) textInput.value = this.workingPreferences[prefKey];
            }
        }

        // Update sliders
        const radiusSlider = document.getElementById('dashboardBorderRadius');
        if (radiusSlider && this.workingPreferences.dashboard_border_radius) {
            radiusSlider.value = this.workingPreferences.dashboard_border_radius;
            const borderRadiusValue = document.getElementById('borderRadiusValue');
            if (borderRadiusValue) borderRadiusValue.textContent = this.workingPreferences.dashboard_border_radius + 'px';
        }

        const paddingSlider = document.getElementById('dashboardCardPadding');
        if (paddingSlider && this.workingPreferences.dashboard_card_padding) {
            paddingSlider.value = this.workingPreferences.dashboard_card_padding;
            const cardPaddingValue = document.getElementById('cardPaddingValue');
            if (cardPaddingValue) cardPaddingValue.textContent = this.workingPreferences.dashboard_card_padding + 'px';
        }
    }

    setupDashboardEventListeners() {
        // Color pickers - update workingPreferences + live preview
        const colorMappings = {
            dashboardPageBg: 'dashboard_page_bg',
            dashboardSidebarBg: 'dashboard_sidebar_bg',
            dashboardCardBg: 'dashboard_card_bg',
            dashboardHeaderBg: 'dashboard_header_bg',
            dashboardPrimaryGreen: 'dashboard_primary',
            dashboardTextPrimary: 'dashboard_text_primary'
        };

        for (const [elementId, prefKey] of Object.entries(colorMappings)) {
            const colorPicker = document.getElementById(elementId);
            const textInput = document.getElementById(elementId + 'Text');

            if (colorPicker) {
                colorPicker.addEventListener('input', (e) => {
                    const value = e.target.value;
                    if (textInput) textInput.value = value;
                    this.workingPreferences[prefKey] = value;
                    this.applyDashboardColors(); // Live preview
                    // NO AUTO-SAVE
                });
            }

            if (textInput) {
                textInput.addEventListener('input', (e) => {
                    const value = e.target.value;
                    if (colorPicker) colorPicker.value = value;
                    this.workingPreferences[prefKey] = value;
                    this.applyDashboardColors(); // Live preview
                    // NO AUTO-SAVE
                });
            }
        }

        // Sliders - live preview
        const radiusSlider = document.getElementById('dashboardBorderRadius');
        if (radiusSlider) {
            radiusSlider.addEventListener('input', (e) => {
                const value = parseInt(e.target.value);
                this.workingPreferences.dashboard_border_radius = value;
                const borderRadiusValue = document.getElementById('borderRadiusValue');
                if (borderRadiusValue) borderRadiusValue.textContent = value + 'px';
                this.applyDashboardColors(); // Live preview
                // NO AUTO-SAVE
            });
        }

        const paddingSlider = document.getElementById('dashboardCardPadding');
        if (paddingSlider) {
            paddingSlider.addEventListener('input', (e) => {
                const value = parseInt(e.target.value);
                this.workingPreferences.dashboard_card_padding = value;
                const cardPaddingValue = document.getElementById('cardPaddingValue');
                if (cardPaddingValue) cardPaddingValue.textContent = value + 'px';
                this.applyDashboardColors(); // Live preview
                // NO AUTO-SAVE
            });
        }

        // Preset buttons - update workingPreferences with live preview
        const presetButtons = ['dashboardPresetDefault', 'dashboardPresetDark', 'dashboardPresetBlue', 'dashboardPresetPurple'];
        presetButtons.forEach(btnId => {
            const btn = document.getElementById(btnId);
            if (btn) {
                btn.addEventListener('click', (e) => {
                    const preset = btnId.replace('dashboardPreset', '').toLowerCase();
                    this.applyDashboardPreset(preset);
                    this.syncUIControls();
                    // NO AUTO-SAVE
                });
            }
        });

        // SAVE button - commit workingPreferences to server
        const saveBtn = document.getElementById('saveDashboardPreferences');
        if (saveBtn) {
            saveBtn.addEventListener('click', () => {
                this.saveUserPreferences();
            });
        }

        // RESET button - revert workingPreferences to savedPreferences
        const resetBtn = document.getElementById('resetDashboardPreferences');
        if (resetBtn) {
            resetBtn.addEventListener('click', () => {
                this.resetToSaved();
            });
        }
    }

    applyDashboardPreset(preset) {
        const presetColors = {
            default: {
                dashboard_page_bg: '#f5f7fa',
                dashboard_sidebar_bg: '#ffffff',
                dashboard_card_bg: '#ffffff',
                dashboard_header_bg: '#1a1a2e',
                dashboard_primary: '#10b981',
                dashboard_text_primary: '#111827',
                dashboard_border_radius: 8,
                dashboard_card_padding: 24
            },
            dark: {
                dashboard_page_bg: '#1a1a2e',
                dashboard_sidebar_bg: '#16213e',
                dashboard_card_bg: '#0f3460',
                dashboard_header_bg: '#0a0a0a',
                dashboard_primary: '#00e5a0',
                dashboard_text_primary: '#e8f0ee',
                dashboard_border_radius: 8,
                dashboard_card_padding: 24
            },
            blue: {
                dashboard_page_bg: '#e8f0fe',
                dashboard_sidebar_bg: '#ffffff',
                dashboard_card_bg: '#ffffff',
                dashboard_header_bg: '#1e3a8a',
                dashboard_primary: '#3b82f6',
                dashboard_text_primary: '#1e293b',
                dashboard_border_radius: 8,
                dashboard_card_padding: 24
            },
            purple: {
                dashboard_page_bg: '#f5f0ff',
                dashboard_sidebar_bg: '#ffffff',
                dashboard_card_bg: '#ffffff',
                dashboard_header_bg: '#6d28d9',
                dashboard_primary: '#8b5cf6',
                dashboard_text_primary: '#2d1b4e',
                dashboard_border_radius: 8,
                dashboard_card_padding: 24
            }
        };

        const colors = presetColors[preset];
        if (colors) {
            // Update workingPreferences with preset values
            Object.keys(colors).forEach(key => {
                this.workingPreferences[key] = colors[key];
            });
            this.applyDashboardColors();
        }
    }
}

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
});
