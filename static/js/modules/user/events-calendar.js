/**
 * AFCON360 — Events dashboard calendar + countdown.
 * Renders registered events on a month grid with color-coded dots and a
 * live countdown to the next event. CSP-safe: no inline handlers, navigation
 * reuses the shell's [data-pane-url] delegation.
 */
(function () {
    function pad(n) { return (n < 10 ? '0' : '') + n; }

    function initCalendar() {
        var dataEl = document.getElementById('eventCalendarData');
        var monthLabel = document.getElementById('calMonthLabel');
        var grid = document.getElementById('calGrid');
        if (!dataEl || !monthLabel || !grid) return;

        var events = [];
        try { events = JSON.parse(dataEl.textContent || '[]'); } catch (e) { events = []; }

        var byDate = {};
        events.forEach(function (ev) {
            if (!ev.date) return;
            (byDate[ev.date] = byDate[ev.date] || []).push(ev);
        });

        var now = new Date();
        var viewYear = now.getFullYear();
        var viewMonth = now.getMonth();
        var monthNames = ['January', 'February', 'March', 'April', 'May', 'June',
            'July', 'August', 'September', 'October', 'November', 'December'];

        function openEvent(url) {
            if (!url) return;
            var a = document.createElement('a');
            a.href = url;
            a.setAttribute('data-pane-url', url);
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        }

        function render() {
            monthLabel.textContent = monthNames[viewMonth] + ' ' + viewYear;
            grid.innerHTML = '';

            var first = new Date(viewYear, viewMonth, 1);
            var startDay = first.getDay();
            var daysInMonth = new Date(viewYear, viewMonth + 1, 0).getDate();

            for (var i = 0; i < startDay; i++) {
                var blank = document.createElement('div');
                blank.className = 'afc-cal-cell afc-cal-blank';
                grid.appendChild(blank);
            }

            for (var d = 1; d <= daysInMonth; d++) {
                var cell = document.createElement('div');
                cell.className = 'afc-cal-cell';
                var iso = viewYear + '-' + pad(viewMonth + 1) + '-' + pad(d);

                var num = document.createElement('span');
                num.className = 'afc-cal-num';
                num.textContent = d;
                cell.appendChild(num);

                var evs = byDate[iso];
                if (evs && evs.length) {
                    cell.classList.add('afc-cal-has-event');
                    var dots = document.createElement('div');
                    dots.className = 'afc-cal-dots';
                    evs.forEach(function (ev) {
                        var dot = document.createElement('i');
                        dot.className = 'afc-dot ' + (ev.status === 'past' ? 'afc-dot-past' : 'afc-dot-upcoming');
                        dots.appendChild(dot);
                    });
                    cell.appendChild(dots);
                    cell.title = evs.map(function (e) { return e.name; }).join(', ');

                    var primary = evs[0];
                    if (primary.url) {
                        cell.style.cursor = 'pointer';
                        cell.addEventListener('click', (function (url) {
                            return function () { openEvent(url); };
                        })(primary.url));
                    }
                }
                grid.appendChild(cell);
            }
        }

        var prev = document.getElementById('calPrev');
        var next = document.getElementById('calNext');
        if (prev && !prev.dataset.afcInit) {
            prev.dataset.afcInit = '1';
            prev.addEventListener('click', function () {
                viewMonth--; if (viewMonth < 0) { viewMonth = 11; viewYear--; } render();
            });
        }
        if (next && !next.dataset.afcInit) {
            next.dataset.afcInit = '1';
            next.addEventListener('click', function () {
                viewMonth++; if (viewMonth > 11) { viewMonth = 0; viewYear++; } render();
            });
        }

        render();
    }

    function initCountdown() {
        var el = document.getElementById('nextEventCountdown');
        if (!el || el.dataset.afcInit) return;
        el.dataset.afcInit = '1';

        var valueEl = el.querySelector('.afc-countdown-value');
        var target = new Date(el.getAttribute('data-target'));
        if (isNaN(target.getTime())) { if (valueEl) valueEl.textContent = ''; return; }

        function tick() {
            var diff = target.getTime() - Date.now();
            if (diff <= 0) { if (valueEl) valueEl.textContent = 'Happening now'; return; }
            var days = Math.floor(diff / 86400000);
            var hrs = Math.floor((diff % 86400000) / 3600000);
            var mins = Math.floor((diff % 3600000) / 60000);
            if (valueEl) valueEl.textContent = days + 'd ' + hrs + 'h ' + mins + 'm';
        }
        tick();
        setInterval(tick, 60000);
    }

    function initReminderCountdowns() {
        document.querySelectorAll('.afc-reminder-countdown').forEach(function (el) {
            if (el.dataset.afcInit) return;
            el.dataset.afcInit = '1';
            var target = new Date(el.getAttribute('data-countdown'));
            if (isNaN(target.getTime())) { el.textContent = ''; return; }
            function tick() {
                var diff = target.getTime() - Date.now();
                if (diff <= 0) { el.textContent = 'Happening now'; return; }
                var d = Math.floor(diff / 86400000);
                var h = Math.floor((diff % 86400000) / 3600000);
                var m = Math.floor((diff % 3600000) / 60000);
                var parts = [];
                if (d) parts.push(d + 'd');
                if (h || d) parts.push(h + 'h');
                parts.push(m + 'm');
                el.textContent = 'Starts in ' + parts.join(' ');
            }
            tick();
            setInterval(tick, 60000);
        });
    }

    function ready(fn) {
        if (document.readyState !== 'loading') fn();
        else document.addEventListener('DOMContentLoaded', fn);
    }

    ready(function () { initCalendar(); initCountdown(); initReminderCountdowns(); });
})();
