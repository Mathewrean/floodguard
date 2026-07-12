const DASHBOARD_DEFAULT_LOCATION = { lat: -1.2921, lng: 36.8219 };

function statusBadge(status) {
    return `<span class="status-badge ${status}">${status}</span>`;
}

function timeAgo(dateString) {
    const seconds = Math.floor((Date.now() - new Date(dateString).getTime()) / 1000);
    if (seconds < 60) return `${seconds}s ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)}m ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)}h ago`;
    return `${Math.floor(seconds / 86400)}d ago`;
}

function getRiskBand(score) {
    if (score >= 0.85) return { label: 'CRITICAL', colour: '#dc2626' };
    if (score >= 0.7) return { label: 'HIGH', colour: '#ea580c' };
    if (score >= 0.4) return { label: 'MODERATE', colour: '#ca8a04' };
    return { label: 'LOW', colour: '#16a34a' };
}

async function initCitizenDashboard() {
    const [zones, reports, globalCount] = await Promise.all([
        fetchJSON('/api/v1/zones/').then(normaliseList).catch(() => []),
        fetchJSON('/api/v1/reports/?submitted_by=me').then(normaliseList).catch(() => []),
        fetchJSON('/api/v1/zones/').then(r => r.count || r.results?.length || 0).catch(() => 0),
    ]);

    if (document.getElementById('global-zone-count')) {
        document.getElementById('global-zone-count').textContent = globalCount;
    }

    renderNearestZone(zones);
    renderMyReports(reports);
    initReportsMap(reports);
    initAiSummaryCard();
    initGlobalSearch();
    initLocationButton();
}

async function initGlobalSearch() {
    const input = document.getElementById('global-search-input');
    const btn = document.getElementById('global-search-btn');
    const resultsDiv = document.getElementById('global-search-results');
    const tableBody = document.getElementById('global-search-table');
    if (!input || !btn || !resultsDiv || !tableBody) return;

    async function doSearch() {
        const q = input.value.trim();
        let url = '/api/v1/global-search/';
        if (q) {
            url += `?q=${encodeURIComponent(q)}`;
        } else {
            resultsDiv.style.display = 'none';
            return;
        }

        try {
            const data = await fetchJSON(url);
            tableBody.innerHTML = data.results.length ? data.results.map(zone => {
                const band = getRiskBand(zone.risk_score);
                return `<tr>
                    <td><strong>${zone.name}</strong></td>
                    <td style="color:${band.colour};font-weight:bold;">${band.label} (${zone.risk_score})</td>
                    <td>${zone.risk_threshold}</td>
                    <td><a class="btn btn-sm btn-primary" href="/map/#zone-${zone.id}">View</a></td>
                </tr>`;
            }).join('') : '<tr><td colspan="4">No zones found.</td></tr>';
            resultsDiv.style.display = 'block';
        } catch (e) {
            tableBody.innerHTML = `<tr><td colspan="4">Search failed: ${e.message}</td></tr>`;
            resultsDiv.style.display = 'block';
        }
    }

    btn.addEventListener('click', doSearch);
    input.addEventListener('keydown', (e) => { if (e.key === 'Enter') doSearch(); });
}

async function initLocationButton() {
    const btn = document.getElementById('global-location-btn');
    if (!btn) return;

    btn.addEventListener('click', async () => {
        if (!navigator.geolocation) {
            alert('Geolocation is not supported by your browser');
            return;
        }

        btn.disabled = true;
        btn.textContent = 'Locating...';

        try {
            const position = await new Promise((resolve, reject) => {
                navigator.geolocation.getCurrentPosition(resolve, reject, {
                    enableHighAccuracy: true,
                    timeout: 10000,
                    maximumAge: 300000
                });
            });

            const lat = position.coords.latitude;
            const lon = position.coords.longitude;

            const data = await fetchJSON(`/api/v1/nearby-zones/?lat=${lat}&lon=${lon}&limit=10`);
            const tableBody = document.getElementById('global-search-table');
            const resultsDiv = document.getElementById('global-search-results');

            if (tableBody && resultsDiv) {
                tableBody.innerHTML = data.zones.length ? data.zones.map(zone => {
                    const band = getRiskBand(zone.risk_score);
                    return `<tr>
                        <td><strong>${zone.name}</strong><br><small>${zone.distance_approx_km} km away</small></td>
                        <td style="color:${band.colour};font-weight:bold;">${band.label} (${zone.risk_score})</td>
                        <td>${zone.risk_threshold}</td>
                        <td><a class="btn btn-sm btn-primary" href="/map/#zone-${zone.id}">View</a></td>
                    </tr>`;
                }).join('') : '<tr><td colspan="4">No zones found near your location.</td></tr>';
                resultsDiv.style.display = 'block';
            }
        } catch (e) {
            alert('Unable to retrieve your location: ' + e.message);
        } finally {
            btn.disabled = false;
            btn.textContent = 'Use My Location';
        }
    });
}

async function initAiSummaryCard() {
    const container = document.getElementById('ai-summary');
    if (!container || typeof window.fetchAiAnalysis !== 'function' || typeof window.renderAiSummaryCard !== 'function') return;

    async function refresh() {
        try {
            const data = await window.fetchAiAnalysis();
            window.renderAiSummaryCard(container, data.analysis || {}, { showSafeZones: true, showOutlook: true });
        } catch (error) {
            container.innerHTML = '<span class="badge low">UNKNOWN</span><p>Flood intelligence is temporarily unavailable.</p>';
        }
    }

    refresh();
    setInterval(refresh, 300000);
}

function renderNearestZone(zones) {
    const risk = document.getElementById('nearest-zone-risk');
    const name = document.getElementById('nearest-zone-name');
    if (!risk || !name) return;
    if (!zones.length) {
        risk.textContent = '--';
        name.textContent = 'No zones configured';
        return;
    }

    const zone = [...zones].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0))[0];
    const band = getRiskBand(zone.risk_score);
    risk.textContent = band.label;
    risk.style.color = band.colour;
    name.textContent = zone.name;
}

function renderMyReports(reports) {
    const table = document.getElementById('my-reports-table');
    const count = document.getElementById('my-reports-count');
    const verified = document.getElementById('verified-reports-count');
    if (count) count.textContent = reports.length;
    if (verified) verified.textContent = reports.filter(report => report.status === 'verified').count || reports.filter(report => report.status === 'verified').length;
    if (!table) return;

    table.innerHTML = reports.length ? reports.map(report => `
        <tr>
            <td>${statusBadge(report.status)}</td>
            <td>${report.severity}</td>
            <td>${timeAgo(report.created_at)}</td>
            <td>${report.description}</td>
        </tr>
    `).join('') : '<tr><td colspan="4">No reports submitted yet.</td></tr>';
}

function initReportsMap(reports) {
    const element = document.getElementById('reports-map');
    if (!element || typeof L === 'undefined' || element._leaflet_id) return;
    const map = L.map('reports-map').setView(
        [DASHBOARD_DEFAULT_LOCATION.lat, DASHBOARD_DEFAULT_LOCATION.lng],
        12
    );
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);

    reports.forEach(report => {
        if (!report.location || !report.location.coordinates) return;
        const [lon, lat] = report.location.coordinates;
        L.circleMarker([lat, lon], {
            radius: 7,
            color: '#fff',
            fillColor: '#2E75B6',
            fillOpacity: .9,
            weight: 2
        }).bindPopup(report.description).addTo(map);
    });
}

document.addEventListener('DOMContentLoaded', initCitizenDashboard);
window.initCitizenDashboard = initCitizenDashboard;
