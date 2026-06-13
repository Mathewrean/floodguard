let alertSocket = null;
let reconnectTimer = null;
let reconnectCount = 0;

function safeAlertText(value) {
    if (window.escapeHTML) return window.escapeHTML(value);
    const template = document.createElement('template');
    template.textContent = value == null ? '' : String(value);
    return template.innerHTML;
}

function setWsStatus(text, colour) {
    const indicator = document.getElementById('ws-status');
    if (!indicator) return;
    indicator.textContent = text;
    indicator.style.color = colour;
}

function initAlertSocket() {
    if (alertSocket && alertSocket.readyState === WebSocket.OPEN) return;

    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    alertSocket = new WebSocket(`${proto}//${window.location.host}/ws/alerts/`);

    alertSocket.onopen = () => {
        reconnectCount = 0;
        console.info('Alert WebSocket connected');
        setWsStatus('Live', '#059669');
    };

    alertSocket.onclose = (e) => {
        if (e.wasClean) return;
        const delay = Math.min(2000 * Math.pow(2, reconnectCount), 30000);
        reconnectCount += 1;
        console.info(`Alert WebSocket closed - reconnecting in ${delay}ms`);
        setWsStatus('Reconnecting...', '#D97706');
        clearTimeout(reconnectTimer);
        reconnectTimer = setTimeout(initAlertSocket, delay);
    };

    alertSocket.onerror = () => {
        // onclose handles reconnect scheduling.
    };

    alertSocket.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data);
            if (data.type === 'connected') return;
            if (data.type === 'flood.update') handleFloodUpdate(data);
            if (data.type === 'alert_message' || data.message) handleAlertMessage(data);
        } catch (err) {
            console.warn('Alert WS message parse error:', err);
        }
    };
}

function handleFloodUpdate(data) {
    const pill = document.querySelector(`[data-zone-id="${data.zone_id}"]`);
    if (!pill) return;
    const score = Number(data.risk_score || 0);
    const band = getRiskBand(score);
    const colour = band.colour;
    pill.style.borderColor = colour;
    pill.style.color = colour;
    pill.textContent = `${data.zone_name || 'Zone'}: ${band.label}`;
}

function handleAlertMessage(data) {
    const message = data.message || `${data.zone_name || 'FloodGuard'} alert issued`;
    const track = document.querySelector('.ticker-track');
    if (track) {
        track.innerHTML = `${safeAlertText(message)} &bull; ${track.innerHTML}`;
    }
    showToast(message, data.severity);
}

function showToast(message, severity) {
    const toast = document.createElement('div');
    toast.className = `alert-notification ${severity ? String(severity).toLowerCase() : ''}`;
    toast.innerHTML = `
        <div class="alert-content">
            <strong>Flood Alert:</strong> ${safeAlertText(message)}
            <br>
            <small>${new Date().toLocaleTimeString()}</small>
        </div>
    `;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 8000);
}

document.addEventListener('DOMContentLoaded', () => {
    if (document.querySelector('.ticker-track') || document.getElementById('map')) {
        initAlertSocket();
    }
});

window.initAlertSocket = initAlertSocket;
