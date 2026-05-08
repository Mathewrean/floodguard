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

async function initCitizenDashboard() {
    const [zones, reports] = await Promise.all([
        fetchJSON('/api/v1/zones/').then(normaliseList).catch(() => []),
        fetchJSON('/api/v1/reports/?submitted_by=me').then(normaliseList).catch(() => []),
    ]);

    renderNearestZone(zones);
    renderMyReports(reports);
    initReportsMap(reports);
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
    risk.textContent = `${(Number(zone.risk_score || 0) * 100).toFixed(0)}%`;
    name.textContent = zone.name;
}

function renderMyReports(reports) {
    const table = document.getElementById('my-reports-table');
    const count = document.getElementById('my-reports-count');
    const verified = document.getElementById('verified-reports-count');
    if (count) count.textContent = reports.length;
    if (verified) verified.textContent = reports.filter(report => report.status === 'verified').length;
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
    const map = L.map('reports-map').setView([-1.2921, 36.8219], 12);
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
