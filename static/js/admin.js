async function initAdminDashboard() {
    await Promise.all([
        renderHealth(),
        renderZoneManagement(),
    ]);
}

async function renderHealth() {
    try {
        const health = await fetchJSON('/health/');
        const system = document.getElementById('system-health');
        const celery = document.getElementById('celery-status');
        const redis = document.getElementById('redis-status');
        const celeryDot = document.getElementById('celery-dot');
        const redisDot = document.getElementById('redis-dot');
        const lastPoll = document.getElementById('last-poll-time');

        if (system) system.textContent = health.status === 'ok' ? 'OK' : 'Check';
        if (celery) celery.textContent = health.celery_status || 'unknown';
        if (redis) redis.textContent = health.redis_status || 'unknown';
        setDot(celeryDot, health.celery_status);
        setDot(redisDot, health.redis_status);
        if (lastPoll) lastPoll.textContent = health.last_poll_time ? timeAgo(health.last_poll_time) : 'just now';
    } catch (error) {
        const system = document.getElementById('system-health');
        if (system) system.textContent = 'Down';
    }
}

function setDot(dot, status) {
    if (!dot) return;
    dot.classList.remove('ok', 'unknown', 'down');
    dot.classList.add(status === 'ok' || status === 'healthy' ? 'ok' : status === 'down' ? 'down' : 'unknown');
}

async function renderZoneManagement() {
    const table = document.getElementById('zone-management-table');
    if (!table) return;
    const zones = await fetchJSON('/api/v1/zones/').then(normaliseList).catch(() => []);
    table.innerHTML = zones.length ? zones.map(zone => {
        const score = Number(zone.risk_score || 0);
        return `
            <tr>
                <td>${zone.name}</td>
                <td><div class="risk-bar"><span style="width:${Math.round(score * 100)}%"></span></div> ${(score * 100).toFixed(0)}%</td>
                <td>${(Number(zone.risk_threshold || 0) * 100).toFixed(0)}%</td>
                <td><a class="btn btn-sm btn-outline" href="/admin/core/alertzone/${zone.id}/change/">Edit</a></td>
            </tr>
        `;
    }).join('') : '<tr><td colspan="4">No zones configured.</td></tr>';
}

document.addEventListener('DOMContentLoaded', initAdminDashboard);
window.initAdminDashboard = initAdminDashboard;
