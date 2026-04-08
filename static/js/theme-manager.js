/**
 * AFCON 360 Theme Manager
 * Handles user preferences, live preview, and theme switching
 * Version: 1.0.0
 */

class ThemeManager {
    constructor() {
        this.preferences = null;
        this.initialized = false;
        this.previewMode = false;
        this.init();
    }

    async init() {
        try {
            // Load user preferences from server
            await this.loadPreferences();

            // Apply preferences to DOM
            this.applyPreferences();

            // Setup event listeners for preference controls
            this.setupEventListeners();

            // Listen for system dark mode changes
            this.setupSystemDarkModeListener();

            this.initialized = true;
            console.log('Theme Manager initialized');
        } catch (error) {
            console.error('Theme Manager initialization failed:', error);
        }
    }

    async loadPreferences() {
        try {
            const response = await fetch('/theme/api/preferences');
            if (response.ok) {
                this.preferences = await response.json();
            } else {
                this.preferences = this.getDefaultPreferences();
            }
        } catch (e) {
            console.warn('Could not load preferences, using defaults');
            this.preferences = this.getDefaultPreferences();
        }
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
            custom_accent: null
        };
    }

    applyPreferences() {
        if (!this.preferences) return;

        // Apply font scale
        document.documentElement.style.setProperty('--user-font-scale', this.preferences.font_scale);

        // Apply font family for dyslexia
        if (this.preferences.dyslexic_font) {
            document.body.classList.add('dyslexic-font');
        } else {
            document.body.classList.remove('dyslexic-font');
        }

        // Apply high contrast mode
        this.applyHighContrast(this.preferences.high_contrast);

        // Apply color blindness filter
        this.applyColorBlindMode(this.preferences.color_blind_mode);

        // Apply dark/light mode
        this.applyDarkMode(this.preferences.dark_mode);

        // Apply reduced motion
        if (this.preferences.reduced_motion) {
            document.body.classList.add('reduced-motion');
        } else {
            document.body.classList.remove('reduced-motion');
        }

        // Apply reading width
        this.applyReadingWidth(this.preferences.reading_width);

        // Apply compact mode
        if (this.preferences.compact_mode) {
            document.body.classList.add('compact-mode');
        } else {
            document.body.classList.remove('compact-mode');
        }

        // Apply custom accent color
        if (this.preferences.custom_accent) {
            document.documentElement.style.setProperty('--brand-primary', this.preferences.custom_accent);
            const rgb = this.hexToRgb(this.preferences.custom_accent);
            document.documentElement.style.setProperty('--brand-primary-rgb', `${rgb.r}, ${rgb.g}, ${rgb.b}`);
        } else {
            // Reset to default (will be overridden by global CSS)
            document.documentElement.style.removeProperty('--brand-primary');
            document.documentElement.style.removeProperty('--brand-primary-rgb');
        }
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

    async updatePreference(key, value) {
        this.preferences[key] = value;
        this.applyPreferences();

        // Save to server
        try {
            const response = await fetch('/theme/preferences/save', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                },
                body: JSON.stringify(this.preferences)
            });

            if (response.ok) {
                console.log(`Preference ${key} saved:`, value);
                this.showToast('Preferences saved', 'success');
            } else {
                console.error('Failed to save preference');
                this.showToast('Failed to save preferences', 'error');
            }
        } catch (error) {
            console.error('Error saving preference:', error);
        }
    }

    async resetToDefaults() {
        this.preferences = this.getDefaultPreferences();
        this.applyPreferences();

        try {
            const response = await fetch('/theme/reset', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                    'X-CSRF-Token': this.getCsrfToken()
                }
            });

            if (response.ok) {
                this.showToast('Preferences reset to defaults', 'success');
                this.updatePreviewControls();
            }
        } catch (error) {
            console.error('Error resetting preferences:', error);
        }
    }

    setupEventListeners() {
        // Font size slider
        const fontSizeSlider = document.getElementById('fontSizeSlider');
        const fontSizeValue = document.getElementById('fontSizeValue');
        if (fontSizeSlider) {
            fontSizeSlider.value = this.preferences.font_scale;
            fontSizeSlider.addEventListener('input', (e) => {
                const value = parseFloat(e.target.value);
                if (fontSizeValue) fontSizeValue.textContent = value.toFixed(1) + 'x';
                this.updatePreference('font_scale', value);
            });
        }

        // Dyslexic font toggle
        const dyslexicToggle = document.getElementById('dyslexicFont');
        if (dyslexicToggle) {
            dyslexicToggle.checked = this.preferences.dyslexic_font;
            dyslexicToggle.addEventListener('change', (e) => {
                this.updatePreference('dyslexic_font', e.target.checked);
            });
        }

        // High contrast radios
        const contrastRadios = document.querySelectorAll('input[name="highContrast"]');
        contrastRadios.forEach(radio => {
            if (radio.value === this.preferences.high_contrast) {
                radio.checked = true;
            }
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.updatePreference('high_contrast', e.target.value);
                }
            });
        });

        // Color blind mode select
        const colorBlindSelect = document.getElementById('colorBlindMode');
        if (colorBlindSelect) {
            colorBlindSelect.value = this.preferences.color_blind_mode;
            colorBlindSelect.addEventListener('change', (e) => {
                this.updatePreference('color_blind_mode', e.target.value);
            });
        }

        // Dark mode radios
        const darkModeRadios = document.querySelectorAll('input[name="darkMode"]');
        darkModeRadios.forEach(radio => {
            if (radio.value === this.preferences.dark_mode) {
                radio.checked = true;
            }
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.updatePreference('dark_mode', e.target.value);
                }
            });
        });

        // Reduced motion toggle
        const reducedMotionToggle = document.getElementById('reducedMotion');
        if (reducedMotionToggle) {
            reducedMotionToggle.checked = this.preferences.reduced_motion;
            reducedMotionToggle.addEventListener('change', (e) => {
                this.updatePreference('reduced_motion', e.target.checked);
            });
        }

        // Reading width radios
        const widthRadios = document.querySelectorAll('input[name="readingWidth"]');
        widthRadios.forEach(radio => {
            if (radio.value === this.preferences.reading_width) {
                radio.checked = true;
            }
            radio.addEventListener('change', (e) => {
                if (e.target.checked) {
                    this.updatePreference('reading_width', e.target.value);
                }
            });
        });

        // Compact mode toggle
        const compactToggle = document.getElementById('compactMode');
        if (compactToggle) {
            compactToggle.checked = this.preferences.compact_mode;
            compactToggle.addEventListener('change', (e) => {
                this.updatePreference('compact_mode', e.target.checked);
            });
        }

        // Custom accent color
        const accentPicker = document.getElementById('customAccent');
        if (accentPicker) {
            accentPicker.value = this.preferences.custom_accent || '#2d5a2d';
            accentPicker.addEventListener('change', (e) => {
                this.updatePreference('custom_accent', e.target.value);
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
        const fontSizeSlider = document.getElementById('fontSizeSlider');
        if (fontSizeSlider) fontSizeSlider.value = this.preferences.font_scale;

        const dyslexicToggle = document.getElementById('dyslexicFont');
        if (dyslexicToggle) dyslexicToggle.checked = this.preferences.dyslexic_font;

        const reducedMotionToggle = document.getElementById('reducedMotion');
        if (reducedMotionToggle) reducedMotionToggle.checked = this.preferences.reduced_motion;

        const compactToggle = document.getElementById('compactMode');
        if (compactToggle) compactToggle.checked = this.preferences.compact_mode;

        const colorBlindSelect = document.getElementById('colorBlindMode');
        if (colorBlindSelect) colorBlindSelect.value = this.preferences.color_blind_mode;

        const accentPicker = document.getElementById('customAccent');
        if (accentPicker) accentPicker.value = this.preferences.custom_accent || '#2d5a2d';
    }

    setupSystemDarkModeListener() {
        if (window.matchMedia) {
            const darkModeQuery = window.matchMedia('(prefers-color-scheme: dark)');
            darkModeQuery.addEventListener('change', (e) => {
                if (this.preferences.dark_mode === 'system') {
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
        const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
        return result ? {
            r: parseInt(result[1], 16),
            g: parseInt(result[2], 16),
            b: parseInt(result[3], 16)
        } : { r: 45, g: 90, b: 45 };
    }

    showToast(message, type = 'info') {
        // Create toast element if it doesn't exist
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

// Auto-initialize when DOM is ready
document.addEventListener('DOMContentLoaded', () => {
    window.themeManager = new ThemeManager();
});
