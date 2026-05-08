function normaliseList(data) {
    return Array.isArray(data) ? data : (data.results || []);
}

function riskClass(score) {
    if (score > 0.7) return 'danger';
    if (score > 0.4) return 'warning';
    return 'safe';
}

function getCookie(name) {
    const value = `; ${document.cookie}`;
    const parts = value.split(`; ${name}=`);
    if (parts.length === 2) return parts.pop().split(';').shift();
    return '';
}

function timeAgo(dateString) {
    const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

function countUp(element, target, duration = 1500) {
    const numericTarget = Number(target) || 0;
    const start = performance.now();
    const initial = Number(element.textContent.replace(/[^\d.-]/g, '')) || 0;

    function tick(now) {
        const progress = Math.min((now - start) / duration, 1);
        const eased = 1 - Math.pow(1 - progress, 3);
        const value = Math.round(initial + (numericTarget - initial) * eased);
        element.textContent = value.toLocaleString();
        if (progress < 1) requestAnimationFrame(tick);
    }

    requestAnimationFrame(tick);
}

async function fetchJSON(url, options = {}) {
    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json();
}

async function initLiveStats() {
    const statElements = document.querySelectorAll('.stat-value[data-stat]');
    if (!statElements.length) return;

    async function refresh() {
        let stats;
        try {
            stats = await fetchJSON('/api/v1/stats/');
        } catch (error) {
            const [zones, readings] = await Promise.all([
                fetchJSON('/api/v1/zones/').then(normaliseList),
                fetchJSON('/api/v1/readings/').then(normaliseList),
            ]);
            stats = {
                zones_count: zones.length,
                alerts_today: 0,
                reports_this_week: readings.length,
                high_risk_zones: zones.filter(zone => Number(zone.risk_score || 0) > 0.7).length,
            };
        }

        statElements.forEach(element => {
            const key = element.dataset.stat;
            if (Object.prototype.hasOwnProperty.call(stats, key)) {
                countUp(element, stats[key]);
            }
        });
    }

    refresh();
    setInterval(refresh, 60000);
}

async function initStatusStrip() {
    const strip = document.getElementById('status-strip');
    if (!strip) return;

    async function refresh() {
        try {
            const zones = normaliseList(await fetchJSON('/api/v1/zones/'));
            strip.innerHTML = zones.length ? zones.map(zone => {
                const score = Number(zone.risk_score || 0);
                return `<span class="zone-pill ${riskClass(score)}">${zone.name}: ${(score * 100).toFixed(0)}%</span>`;
            }).join('') : '<span class="zone-pill safe">No zones configured</span>';
        } catch (error) {
            strip.innerHTML = '<span class="zone-pill warning">Zone status unavailable</span>';
        }
    }

    refresh();
    setInterval(refresh, 60000);
}

async function initAlertsTicker() {
    const ticker = document.getElementById('alerts-ticker');
    if (!ticker) return;
    const track = ticker.querySelector('.ticker-track') || ticker;

    async function refresh() {
        try {
            const alerts = normaliseList(await fetchJSON('/api/v1/alerts/')).slice(0, 5);
            if (!alerts.length) {
                track.textContent = 'No alerts issued yet';
                return;
            }
            track.innerHTML = alerts.map(alert => {
                const message = alert.message || `${alert.zone_name || 'Zone'} alert`;
                const critical = /critical|evacuat|danger|high/i.test(message);
                return `<span class="${critical ? 'ticker-critical' : ''}">${message}</span>`;
            }).join(' • ');
        } catch (error) {
            track.textContent = 'Latest alerts unavailable';
        }
    }

    refresh();
    setInterval(refresh, 30000);
}

function initHamburgerMenu() {
    const nav = document.querySelector('.navbar');
    const toggle = document.querySelector('.mobile-menu-toggle');
    if (!nav || !toggle) return;

    toggle.addEventListener('click', event => {
        event.stopPropagation();
        const isOpen = nav.classList.toggle('nav-mobile-open');
        toggle.setAttribute('aria-expanded', String(isOpen));
    });

    document.addEventListener('click', event => {
        if (!nav.contains(event.target)) {
            nav.classList.remove('nav-mobile-open');
            toggle.setAttribute('aria-expanded', 'false');
        }
    });
}

function markActiveNav() {
    const path = window.location.pathname;
    document.querySelectorAll('.nav-menu a').forEach(link => {
        if (link.getAttribute('href') === path) link.classList.add('active');
    });
}

document.addEventListener('DOMContentLoaded', function() {
    markActiveNav();
    initHamburgerMenu();
    initLiveStats();
    initStatusStrip();
    initAlertsTicker();
});

window.countUp = countUp;
window.fetchJSON = fetchJSON;
window.normaliseList = normaliseList;
window.riskClass = riskClass;
window.getCookie = getCookie;
window.timeAgo = timeAgo;
