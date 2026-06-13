async function initAuthorityDashboard() {
    await Promise.all([
        renderPendingReports(),
        renderFloodZones(),
        refreshPendingCount(),
    ]);
    connectFloodMapSocket();
}

async function refreshPendingCount() {
    const reports = await fetchJSON('/api/v1/reports/?status=pending').then(normaliseList).catch(() => []);
    const count = document.getElementById('pending-reports-count');
    if (count) count.textContent = reports.length;
}

async function renderPendingReports() {
    const table = document.getElementById('pending-reports-table');
    if (!table) return;
    const reports = await fetchJSON('/api/v1/reports/?status=pending').then(normaliseList).catch(() => []);

    table.innerHTML = reports.length ? reports.map(report => `
        <tr data-report-id="${report.id}">
            <td>#${report.id}</td>
            <td><span class="status-badge ${report.status}">${report.status}</span></td>
            <td>${report.severity}</td>
            <td>${new Date(report.created_at).toLocaleString()}</td>
            <td>${report.description}</td>
            <td>
                <button class="btn btn-sm btn-success" data-action="verified">Verify</button>
                <button class="btn btn-sm btn-danger" data-action="rejected">Reject</button>
            </td>
        </tr>
    `).join('') : '<tr><td colspan="6">No pending reports.</td></tr>';

    table.querySelectorAll('button[data-action]').forEach(button => {
        button.addEventListener('click', () => updateReportStatus(button.closest('tr'), button.dataset.action));
    });
}

async function updateReportStatus(row, status) {
    const id = row.dataset.reportId;
    const response = await fetch(`/api/v1/reports/${id}/verify/`, {
        method: 'PATCH',
        headers: {
            'X-CSRFToken': getCookie('csrftoken'),
            'Content-Type': 'application/json'
        },
        body: JSON.stringify({ status })
    });
    if (response.ok) {
        row.remove();
        refreshPendingCount();
    }
}

async function renderFloodZones() {
    const container = document.getElementById('zones-list');
    if (!container) return;
    const zones = await fetchJSON('/api/v1/zones/').then(normaliseList).catch(() => []);
    container.innerHTML = zones.length ? zones.map(zone => {
        const score = Number(zone.risk_score || 0);
        const band = getRiskBand(score);
        return `
            <div class="card zone-card ${riskClass(score)}" data-zone-id="${zone.id}">
                <h3 class="card-title">${zone.name}</h3>
                <span class="zone-risk ${riskClass(score)}">${(score * 100).toFixed(0)}% ${band.label}</span>
                <p class="card-meta">Threshold ${(Number(zone.risk_threshold || 0) * 100).toFixed(0)}%</p>
                <div class="risk-bar"><span style="width:${Math.round(score * 100)}%"></span></div>
            </div>
        `;
    }).join('') : '<p class="card-meta">No zones configured.</p>';
}

function connectFloodMapSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const socket = new WebSocket(`${protocol}//${window.location.host}/ws/flood-map/`);
    socket.onmessage = event => {
        const data = JSON.parse(event.data);
        const zoneId = data.zone_id || data.id;
        const score = Number(data.risk_score);
        if (!zoneId || Number.isNaN(score)) return;
        const card = document.querySelector(`[data-zone-id="${zoneId}"]`);
        if (!card) return;
        card.classList.remove('safe', 'warning', 'high', 'critical');
        const band = getRiskBand(score);
        card.classList.add(band.className);
        const badge = card.querySelector('.zone-risk');
        if (badge) badge.textContent = `${(score * 100).toFixed(0)}% ${band.label}`;
        const bar = card.querySelector('.risk-bar span');
        if (bar) bar.style.width = `${Math.round(score * 100)}%`;
    };
    socket.onerror = () => socket.close();
}

document.addEventListener('DOMContentLoaded', initAuthorityDashboard);
window.initAuthorityDashboard = initAuthorityDashboard;
