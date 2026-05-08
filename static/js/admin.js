/**
 * Admin Dashboard - Global Command Center
 * Handles global map, heatmap, zone monitoring, real-time alerts
 */

let adminMap = null;
let zonesLayer = null;
let heatmapLayer = null;
let zoneMarkers = [];

// Initialize admin dashboard
document.addEventListener('DOMContentLoaded', function() {
    initAdminMap();
    fetchZones();
    fetchDashboardStats();
    initAlertsFeed();
    
    // Setup controls
    document.getElementById('show-heatmap').addEventListener('change', toggleHeatmap);
    document.getElementById('show-clusters').addEventListener('change', toggleClusters);
    
    // Refresh data every 30 seconds
    setInterval(fetchZones, 30000);
    setInterval(fetchDashboardStats, 30000);
});

function initAdminMap() {
    const mapEl = document.getElementById('admin-map');
    if (!mapEl || typeof L === 'undefined') return;
    
    // Use world view initially, will be fitted to zones
    adminMap = L.map('admin-map').setView([0, 0], 2);
    
    addBasemap(adminMap, 0);
    
    // Add scale control
    L.control.scale({ position: 'bottomright' }).addTo(adminMap);
}

function addBasemap(map, index) {
    const BASEMAPS = [
        {
            url: 'https://{s}.basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png',
            options: { subdomains: 'abcd', maxZoom: 19, attribution: '&copy; OpenStreetMap &copy; CARTO' }
        },
        {
            url: 'https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png',
            options: { maxZoom: 19, attribution: '&copy; OpenStreetMap' }
        }
    ];
    
    const provider = BASEMAPS[index] || BASEMAPS[0];
    const layer = L.tileLayer(provider.url, provider.options).addTo(map);
    
    layer.on('tileerror', () => {
        if (index + 1 < BASEMAPS.length && !map._fallbackBasemapLoaded) {
            map._fallbackBasemapLoaded = true;
            map.removeLayer(layer);
            addBasemap(map, index + 1);
        }
    });
}

function fetchZones() {
    fetch('/api/v1/zones/?limit=500')
        .then(r => r.json())
        .then(data => {
            const zones = Array.isArray(data) ? data : (data.results || []);
            renderZones(zones);
            if (zones.length && adminMap) {
                fitMapToZones(zones);
            }
        })
        .catch(err => console.error('Failed to fetch zones:', err));
}

function renderZones(zones) {
    if (!adminMap) return;
    
    // Clear existing layers
    if (zonesLayer) adminMap.removeLayer(zonesLayer);
    zonesLayer = L.layerGroup().addTo(adminMap);
    zoneMarkers = [];
    
    zones.forEach(zone => {
        const score = Number(zone.risk_score || 0);
        const color = zoneColour(score);
        
        // Draw polygon
        const polygon = L.geoJSON(zone.polygon, {
            style: {
                color: color,
                fillColor: color,
                fillOpacity: 0.3,
                weight: 2
            }
        }).bindPopup(`
            <strong>${escapeHTML(zone.name)}</strong><br>
            Risk: ${(score * 100).toFixed(1)}%<br>
            Threshold: ${(zone.risk_threshold * 100).toFixed(1)}%<br>
            Status: ${zoneStatus(score)}<br>
            <button onclick="triggerOverride(${zone.id})" class="btn btn-sm">Override</button>
        `);
        
        polygon.addTo(zonesLayer);
        
        // Calculate centroid for heatmap point
        if (zone.polygon && zone.polygon.centroid) {
            const centroid = zone.polygon.centroid;
            zoneMarkers.push({
                lat: centroid.y,
                lng: centroid.x,
                intensity: score,
                zone: zone
            });
        }
    });
    
    // Update heatmap if enabled
    if (document.getElementById('show-heatmap').checked) {
        updateHeatmap();
    }
}

function fitMapToZones(zones) {
    const bounds = L.latLngBounds();
    let hasValid = false;
    
    zones.forEach(zone => {
        if (zone.polygon && zone.polygon.coordinates) {
            try {
                const latLngs = [];
                const coords = zone.polygon.coordinates[0]; // exterior ring
                coords.forEach(coord => {
                    latLngs.push([coord[1], coord[0]]);  // [lat, lng]
                });
                bounds.extend(L.latLngBounds(latLngs));
                hasValid = true;
            } catch(e) {}
        }
    });
    
    if (hasValid) {
        adminMap.fitBounds(bounds, { padding: [30, 30] });
    } else {
        // Default to Africa if no valid bounds
        adminMap.setView([0, 10], 4);
    }
}

function zoneColour(score) {
    if (score > 0.7) return '#C0392B';
    if (score > 0.4) return '#E67E22';
    return '#27AE60';
}

function zoneStatus(score) {
    if (score > 0.7) return 'HIGH RISK';
    if (score > 0.4) return 'MODERATE';
    return 'SAFE';
}

function toggleHeatmap() {
    if (document.getElementById('show-heatmap').checked) {
        updateHeatmap();
    } else if (heatmapLayer) {
        adminMap.removeLayer(heatmapLayer);
        heatmapLayer = null;
    }
}

function updateHeatmap() {
    if (!adminMap || !document.getElementById('show-heatmap').checked) return;
    
    if (heatmapLayer) adminMap.removeLayer(heatmapLayer);
    
    // Simple circle-based heatmap simulation
    const points = zoneMarkers.map(m => [m.lat, m.lng, m.intensity]);
    
    heatmapLayer = L.layerGroup();
    points.forEach(point => {
        const [lat, lng, intensity] = point;
        const radius = 30000 * intensity + 10000; // 10-40km radius based on risk
        const color = intensity > 0.7 ? '#C0392B' : intensity > 0.4 ? '#E67E22' : '#F59E0B';
        
        L.circle([lat, lng], {
            radius: radius,
            color: color,
            fillColor: color,
            fillOpacity: 0.25 * intensity,
            weight: 1
        }).addTo(heatmapLayer);
    });
    
    heatmapLayer.addTo(adminMap);
}

function toggleClusters() {
    // Cluster visualization toggle
    if (zonesLayer) {
        zonesLayer.eachLayer(layer => {
            if (layer.options && layer.options.cluster) {
                layer.setStyle({ opacity: document.getElementById('show-clusters').checked ? 1 : 0.3 });
            }
        });
    }
}

function fetchDashboardStats() {
    fetch('/api/v1/dashboard/stats/')
        .then(r => r.json())
        .then(stats => {
            document.getElementById('total-zones').textContent = stats.total_zones || 0;
            document.getElementById('critical-zones').textContent = stats.high_risk_zones || 0;
            document.getElementById('pending-reports').textContent = stats.reports_this_week || 0;
            document.getElementById('alerts-24h').textContent = stats.alerts_today || 0;
        })
        .catch(err => console.error('Failed to fetch stats:', err));
}

function fetchAlertsFeed() {
    fetch('/api/v1/alerts/?limit=10')
        .then(r => r.json())
        .then(data => {
            const alerts = Array.isArray(data) ? data : (data.results || []);
            renderAlertsFeed(alerts);
        })
        .catch(err => console.error('Failed to fetch alerts:', err));
}

function renderAlertsFeed(alerts) {
    const container = document.getElementById('alerts-feed');
    if (!alerts.length) {
        container.innerHTML = '<p style="color: #666;">No recent alerts</p>';
        return;
    }
    
    container.innerHTML = alerts.map(alert => `
        <div class="alert-item ${alert.delivery_status}">
            <strong>${escapeHTML(alert.zone_name)}</strong><br>
            <small>${new Date(alert.triggered_at).toLocaleTimeString()}</small><br>
            <span>${escapeHTML(alert.message.substring(0, 100))}...</span>
        </div>
    `).join('');
}

function initAlertsFeed() {
    fetchAlertsFeed();
    setInterval(fetchAlertsFeed, 30000);
}

// Override modal
function triggerOverride(zoneId) {
    document.getElementById('override-zone-id').value = zoneId;
    document.getElementById('override-modal').style.display = 'block';
}

function closeOverrideModal() {
    document.getElementById('override-modal').style.display = 'none';
}

document.getElementById('override-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const zoneId = document.getElementById('override-zone-id').value;
    const duration = parseInt(document.getElementById('override-duration').value);
    
    fetch(`/api/v1/zones/${zoneId}/manual_override/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify({
            active: true,
            duration_hours: duration
        })
    })
    .then(r => r.json())
    .then(data => {
        if (data.status === 'updated') {
            closeOverrideModal();
            fetchZones(); // Refresh map
            showToast('Override activated', 'success');
        } else {
            showToast('Failed to set override', 'error');
        }
    })
    .catch(err => {
        console.error(err);
        showToast('Error setting override', 'error');
    });
});

function showToast(message, type = 'info') {
    const toast = document.createElement('div');
    toast.className = `toast toast-${type}`;
    toast.textContent = message;
    document.body.appendChild(toast);
    setTimeout(() => toast.remove(), 3000);
}
