const API_CACHE = new Map();

// TTL tiers per endpoint (milliseconds)
const TIER_TTLS = {
   '/api/v1/zones/': 60000,
   '/api/v1/readings/': 60000,
   '/api/v1/stats/': 30000,
   '/api/v1/alerts/': 15000,
   '/api/v1/dashboard/stats/': 30000,
   '/api/v1/dynamic-zone/': 10000,
   '/api/v1/h3-cells/': 60000,
   '/api/v1/geocode/': 300000,
   '/api/v1/emergency-services/': 120000,
   default: 10000,
};

window.getRiskBand = function(score) {
        const value = Number(score) || 0;
        if (value >= 0.85) return { label: 'CRITICAL', colour: '#7F1D1D', className: 'critical' };
        if (value >= 0.70) return { label: 'HIGH RISK', colour: '#DC2626', className: 'high' };
        if (value >= 0.40) return { label: 'MODERATE', colour: '#D97706', className: 'warning' };
        return { label: 'SAFE', colour: '#059669', className: 'safe' };
};

function showRateLimitWarning(endpoint) {
    const key = `rl_warned_${endpoint}`;
    if (sessionStorage.getItem(key)) return;
    sessionStorage.setItem(key, '1');

    const banner = document.createElement('div');
    banner.style.cssText = `
      position:fixed; bottom:60px; left:50%;
      transform:translateX(-50%); z-index:9999;
            background:#D97706; color:white; padding:10px 20px;
      border-radius:8px; font-size:13px; font-weight:600;
      box-shadow:0 4px 12px rgba(0,0,0,0.2)
    `;
    banner.textContent = 'API rate limit reached - data refresh paused';
    document.body.appendChild(banner);
    setTimeout(() => banner.remove(), 8000);
}

async function cachedFetch(url, explicitMaxAge) {
    const now = Date.now();
    const maxAge = explicitMaxAge ||
        TIER_TTLS[url] ||
        TIER_TTLS.default;
    const cached = API_CACHE.get(url);
    if (cached && now - cached.time < maxAge) {
        return cached.data;
    }

    try {
        const response = await fetch(url);
        if (!response.ok) {
            if (response.status === 429) {
                API_CACHE.set(url, {
                    data: cached?.data || null,
                    time: now + 50000,
                });
                showRateLimitWarning(url);
                console.warn(`Rate limited on ${url}; backing off for 60s`);
                return cached?.data || null;
            }
            throw new Error(`HTTP ${response.status}`);
        }

        const data = await response.json();
        API_CACHE.set(url, { data, time: now });
        return data;
    } catch (error) {
        console.warn(`API fetch failed for ${url}:`, error.message);
        return cached?.data || null;
    }
}

function normaliseList(data) {
    return Array.isArray(data) ? data : (data.results || []);
}

function escapeHTML(value) {
    const template = document.createElement('template');
    template.textContent = value == null ? '' : String(value);
    return template.innerHTML;
}

function riskClass(score) {
    return window.getRiskBand(score).className;
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
    if (typeof window.cachedFetch === 'function' && (!options || Object.keys(options).length === 0)) {
        const data = await window.cachedFetch(url);
        if (data === null) throw new Error(`${url} returned no data`);
        return data;
    }

    const response = await fetch(url, options);
    if (!response.ok) throw new Error(`${url} returned ${response.status}`);
    return response.json();
}

function initLiveStats() {
    const statElements = document.querySelectorAll('.stat-value[data-stat]');
    if (!statElements.length) return;

    async function refresh() {
        let stats;
        try {
            stats = await fetchJSON('/api/v1/stats/');
        } catch (error) {
            const [zones, readings] = await Promise.all([
                fetchJSON('/api/v1/zones/').then(normaliseList).catch(() => []),
                fetchJSON('/api/v1/readings/').then(normaliseList).catch(() => []),
            ]);
            stats = {
                zones_count: zones.length,
                alerts_today: 0,
                reports_this_week: readings.length,
                high_risk_zones: zones.filter(zone => {
                    const score = Number(zone.risk_score || 0);
                    return score >= 0.7 && score < 0.85;
                }).length,
                critical_zones: zones.filter(zone => Number(zone.risk_score || 0) >= 0.85).length,
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
    // Refresh every 30 seconds
    setInterval(refresh, 30000);
}

async function initStatusStrip() {
    const strip = document.getElementById('status-strip');
    if (!strip) return;

    async function refresh() {
        try {
            const zones = normaliseList(await fetchJSON('/api/v1/zones/'));
            strip.innerHTML = zones.length ? zones.map(zone => {
                const score = Number(zone.risk_score || 0);
                const band = window.getRiskBand(score);
                return `<span class="zone-pill ${band.className}" data-zone-id="${zone.id}" style="color:${band.colour};border-color:${band.colour}">${escapeHTML(zone.name)}: ${band.label}</span>`;
            }).join('') : '<span class="zone-pill standby">Monitoring standby: add flood zones</span>';
        } catch (error) {
            strip.innerHTML = '<span class="zone-pill standby">Zone service reconnecting</span>';
        }
    }

    refresh();
    setInterval(refresh, 30000);
}

async function initAlertsTicker() {
    const ticker = document.getElementById('alerts-ticker');
    if (!ticker) return;
    const track = ticker.querySelector('.ticker-track') || ticker;

    async function refresh() {
        try {
            const alerts = normaliseList(await fetchJSON('/api/v1/alerts/')).slice(0, 5);
            if (!alerts.length) {
                track.textContent = 'No alerts issued yet. FloodGuard is monitoring configured zones.';
                return;
            }
            track.innerHTML = alerts.map(alert => {
                const message = alert.message || `${alert.zone_name || 'Zone'} alert`;
                const critical = /critical|evacuat|danger|high/i.test(message);
                return `<span class="${critical ? 'ticker-critical' : ''}">${escapeHTML(message)}</span>`;
            }).join(' • ');
        } catch (error) {
            track.textContent = 'Alert feed reconnecting. No active alert data is currently available.';
        }
    }

    refresh();
    setInterval(refresh, 15000);
}

function renderRiskLegends() {
    const bands = [0, 0.4, 0.7, 0.85].map(score => window.getRiskBand(score));
    document.querySelectorAll('[data-risk-legend]').forEach(container => {
        container.innerHTML = bands.map(band => `
            <span class="legend-item ${band.className}">
                <i class="legend-dot ${band.className}" style="background:${band.colour}"></i>
                ${band.label}
            </span>
        `).join('');
    });
}

async function fetchAiAnalysis() {
    const response = await fetch('/api/v1/ai-analysis/', {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken') || '',
        },
        body: JSON.stringify({ all: true }),
    });

    if (!response.ok) {
        throw new Error(`HTTP ${response.status}`);
    }

    return response.json();
}

function renderAiSummaryCard(container, analysis, options = {}) {
    if (!container) return;

    const overallRisk = String(analysis.overall_risk || 'UNKNOWN').toUpperCase();
    const summary = analysis.summary || 'Flood intelligence is unavailable right now.';
    const safeZones = Array.isArray(analysis.safe_zones) ? analysis.safe_zones : [];
    const outlook = analysis['24h_outlook'] || '';
    const badgeClass = overallRisk.toLowerCase();
    const pieces = [
        `<span class="badge ${badgeClass}">${escapeHTML(overallRisk)}</span>`,
        `<p>${escapeHTML(summary)}</p>`,
    ];

    if (options.showSafeZones) {
        pieces.push(`<p><strong>Safe zones:</strong> ${safeZones.length ? safeZones.map(escapeHTML).join(', ') : 'None reported'}</p>`);
    }

    if (options.showOutlook && outlook) {
        pieces.push(`<p><strong>24h outlook:</strong> ${escapeHTML(outlook)}</p>`);
    }

    if (options.showActions && Array.isArray(analysis.immediate_actions) && analysis.immediate_actions.length) {
        pieces.push(`<ul>${analysis.immediate_actions.slice(0, 3).map(action => `<li>${escapeHTML(action)}</li>`).join('')}</ul>`);
    }

    container.innerHTML = pieces.join('');
}

async function initLandingAiSummary() {
    const container = document.getElementById('landing-ai-summary');
    if (!container) return;

    async function refresh() {
        try {
            const data = await fetchAiAnalysis();
            renderAiSummaryCard(container, data.analysis || {}, { showSafeZones: false, showOutlook: false });
        } catch (error) {
            container.innerHTML = '<span class="badge low">UNKNOWN</span><p>Flood intelligence is temporarily unavailable.</p>';
        }
    }

    refresh();
    setInterval(refresh, 300000);
}

function initThemeToggle() {
    const toggle = document.getElementById('theme-toggle');
    if (!toggle) return;
    
    const sunIcon = toggle.querySelector('.sun-icon');
    const moonIcon = toggle.querySelector('.moon-icon');
    
    // Check for saved theme preference
    const savedTheme = localStorage.getItem('theme') || 'light';
    document.documentElement.setAttribute('data-theme', savedTheme);
    updateIcons(savedTheme);
    
    toggle.addEventListener('click', () => {
        const currentTheme = document.documentElement.getAttribute('data-theme');
        const newTheme = currentTheme === 'light' ? 'dark' : 'light';
        document.documentElement.setAttribute('data-theme', newTheme);
        localStorage.setItem('theme', newTheme);
        updateIcons(newTheme);
    });
    
    function updateIcons(theme) {
        if (theme === 'dark') {
            sunIcon.style.display = 'block';
            moonIcon.style.display = 'none';
        } else {
            sunIcon.style.display = 'none';
            moonIcon.style.display = 'block';
        }
    }
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

async function initHeroStats() {
    const zonesEl = document.getElementById('hero-zones-count');
    const alertsEl = document.getElementById('hero-alerts-count');
    const reportsEl = document.getElementById('hero-reports-count');
    
    if (!zonesEl && !alertsEl && !reportsEl) return;
    
    try {
        const stats = await fetchJSON('/api/v1/stats/');
        if (zonesEl) zonesEl.textContent = stats.zones_count || 0;
        if (alertsEl) alertsEl.textContent = stats.alerts_today || 0;
        if (reportsEl) reportsEl.textContent = stats.reports_this_week || 0;
    } catch (error) {
        if (zonesEl) zonesEl.textContent = 18;
        if (alertsEl) alertsEl.textContent = 0;
        if (reportsEl) reportsEl.textContent = 0;
    }
}

document.addEventListener('DOMContentLoaded', function() {
    markActiveNav();
    initThemeToggle();
    initHamburgerMenu();
    initLiveStats();
    initHeroStats();
    renderRiskLegends();
    initLandingAiSummary();
    initStatusStrip();
    initAlertsTicker();
});

window.countUp = countUp;
window.cachedFetch = cachedFetch;
window.fetchJSON = fetchJSON;
window.normaliseList = normaliseList;
window.escapeHTML = escapeHTML;
window.riskClass = riskClass;
window.getCookie = getCookie;
window.timeAgo = timeAgo;
window.fetchAiAnalysis = fetchAiAnalysis;
window.renderAiSummaryCard = renderAiSummaryCard;
