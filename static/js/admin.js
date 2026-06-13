/**
 * Admin Dashboard - Global Command Center
 * Handles global map, heatmap, zone monitoring, real-time alerts
 */

let adminMap = null;
let zonesLayer = null;
let heatmapLayer = null;
let zoneMarkers = [];

async function adminApiData(url, maxAge = 10000) {
    if (window.cachedFetch) return window.cachedFetch(url, maxAge);
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

// Initialize admin dashboard
document.addEventListener('DOMContentLoaded', function() {
    initAdminMap();
    fetchZones();
    fetchDashboardStats();
    fetchDataSources();
    initAlertsFeed();
    
    // Setup controls
    document.getElementById('show-heatmap').addEventListener('change', toggleHeatmap);
    document.getElementById('show-clusters').addEventListener('change', toggleClusters);
    
    // WebSocket handles real-time changes; polling is a fallback.
    setInterval(fetchZones, 60000);
    setInterval(fetchDashboardStats, 30000);
    setInterval(fetchDataSources, 30000);
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
    cachedFetch('/api/v1/zones/?limit=500')
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
        
        // Draw polygon with enhanced styling
        const polygon = L.geoJSON(zone.polygon, {
            style: function(feature) {
                return zoneStyle(score, false);
            }
        }).bindPopup(`
            <strong>${escapeHTML(zone.name)}</strong><br>
            Risk: ${(score * 100).toFixed(1)}%<br>
            Threshold: ${(zone.risk_threshold * 100).toFixed(1)}%<br>
            Status: ${zoneStatus(score)}<br>
            <button onclick="triggerOverride(${zone.id})" class="btn btn-sm">Override</button>
            <button onclick="triggerDispatch(${zone.id})" class="btn btn-sm btn-accent">Send Alert</button>
        `);
        
        // Store original style for hover reset
        polygon.riskScore = score;
        polygon.originalStyle = zoneStyle(score, false);
        
        // Hover: bring to front and dim others
        polygon.on('mouseover', function() {
            this.setStyle(zoneStyle(score, true));
            this.bringToFront();
            // Dim all other zones
            zonesLayer.eachLayer(other => {
                if (other !== polygon && other.setStyle) {
                    other.setStyle({ fillOpacity: 0.06, weight: 1 });
                }
            });
        });
        
        polygon.on('mouseout', function() {
            this.setStyle(this.originalStyle);
            // Restore all zones
            zonesLayer.eachLayer(other => {
                if (other.setStyle && other.originalStyle) {
                    other.setStyle(other.originalStyle);
                }
            });
        });
        
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

function zoneStyle(score, isHovered = false) {
    const baseColor = zoneColour(score);
    return {
        color: isHovered ? '#ffffff' : baseColor,
        weight: isHovered ? 4 : 3,
        fillColor: baseColor,
        fillOpacity: isHovered ? 0.25 : 0.12,
        dashArray: score > 0.7 ? null : (score > 0.4 ? '8, 4' : '2, 4'),
        className: 'zone-polygon'
    };
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
    cachedFetch('/api/v1/dashboard/stats/')
        .then(stats => {
            document.getElementById('total-zones').textContent = stats.zones_count || 0;
            document.getElementById('critical-zones').textContent = stats.high_risk_zones || 0;
            document.getElementById('pending-reports').textContent = stats.reports_this_week || 0;
            document.getElementById('alerts-24h').textContent = stats.alerts_today || 0;
        })
        .catch(err => console.error('Failed to fetch stats:', err));
}

function fetchDataSources() {
    adminApiData('/api/v1/data-sources/', 30000)
        .then(data => renderDataSources(data))
        .catch(err => {
            console.error('Failed to fetch data sources:', err);
            const summary = document.getElementById('data-sources-summary');
            if (summary) summary.textContent = 'Unable to load source status';
        });
}

function renderDataSources(data) {
    const sources = data.sources || [];
    const active = data.active_sources || sources.filter(source => source.configured).length;
    const total = sources.length || 6;
    const weatherNames = ['openweather', 'tomorrow_io', 'weather_api'];
    const satelliteNames = ['nasa_gpm', 'google_earth_engine'];
    const weatherActive = sources.filter(source => weatherNames.includes(source.name) && source.configured).length;
    const satelliteActive = sources.filter(source => satelliteNames.includes(source.name) && source.configured).length;

    const activeEl = document.getElementById('data-sources-active');
    const summaryEl = document.getElementById('data-sources-summary');
    const confidenceEl = document.getElementById('data-confidence');
    const openMeteoEl = document.getElementById('source-open-meteo');
    const weatherEl = document.getElementById('source-weather-count');
    const satelliteEl = document.getElementById('source-satellite-count');
    const listEl = document.getElementById('data-sources-list');

    if (activeEl) activeEl.textContent = `${active}/${total}`;
    if (summaryEl) summaryEl.textContent = `${active} of ${total} providers configured`;
    if (confidenceEl) {
        confidenceEl.textContent = `Confidence: ${data.data_confidence || 'low'}`;
        confidenceEl.className = `status-badge ${active >= 3 ? 'verified' : active >= 1 ? 'pending' : 'rejected'}`;
    }
    if (openMeteoEl) openMeteoEl.textContent = sources.find(source => source.name === 'open_meteo')?.configured ? 'OK' : 'Missing';
    if (weatherEl) weatherEl.textContent = `${weatherActive}/3`;
    if (satelliteEl) satelliteEl.textContent = `${satelliteActive}/2`;
    if (listEl) {
        listEl.innerHTML = sources.map(source => {
            const label = source.configured ? 'configured' : 'needs key';
            return `<span class="status-badge ${source.configured ? 'verified' : 'pending'}">${escapeHTML(source.name)}: ${label}</span>`;
        }).join(' ');
    }
}

function fetchAlertsFeed() {
    cachedFetch('/api/v1/alerts/?limit=10')
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
    setInterval(fetchAlertsFeed, 15000);
}

// Override modal
function triggerOverride(zoneId) {
    document.getElementById('override-zone-id').value = zoneId;
    document.getElementById('override-modal').style.display = 'block';
}

function closeOverrideModal() {
    document.getElementById('override-modal').style.display = 'none';
}

function closeOverrideModal() {
    document.getElementById('override-modal').style.display = 'none';
}

// Dispatch alert modal
function triggerDispatch(zoneId) {
    document.getElementById('dispatch-zone-id').value = zoneId;
    document.getElementById('dispatch-result').style.display = 'none';
    document.getElementById('dispatch-message').value = '';
    document.getElementById('dispatch-test-mode').checked = true;
    // Reset channels to default (SMS checked, Email unchecked)
    document.querySelectorAll('input[name="channels"]').forEach(cb => {
        cb.checked = (cb.value === 'sms');
    });
    document.getElementById('dispatch-modal').style.display = 'block';
}

function closeDispatchModal() {
    document.getElementById('dispatch-modal').style.display = 'none';
}

document.getElementById('dispatch-form').addEventListener('submit', function(e) {
    e.preventDefault();
    const zoneId = document.getElementById('dispatch-zone-id').value;

    // Gather selected channels
    const channels = [];
    document.querySelectorAll('input[name="channels"]:checked').forEach(cb => {
        channels.push(cb.value);
    });

    const message = document.getElementById('dispatch-message').value.trim();
    const testMode = document.getElementById('dispatch-test-mode').checked;

    const payload = {
        channels: channels,
        test_mode: testMode
    };
    if (message) {
        payload.test_message = message;
    }

    fetch(`/api/v1/zones/${zoneId}/dispatch_alert/`, {
        method: 'POST',
        headers: {
            'Content-Type': 'application/json',
            'X-CSRFToken': getCookie('csrftoken')
        },
        body: JSON.stringify(payload)
    })
    .then(r => r.json())
    .then(data => {
        const resultDiv = document.getElementById('dispatch-result');
        resultDiv.style.display = 'block';

        if (data.status === 'preview' || data.status === 'dispatched') {
            resultDiv.className = 'alert alert-success';
            const statusText = testMode ? 'TEST PREVIEW' : 'ALERT DISPATCHED';
            let details = `<strong>${statusText}</strong><br>
                Zone: ${data.zone}<br>
                Channels: ${data.channels.join(', ')}<br>
                Target Users: ${data.target_user_count}<br>`;

            if (testMode) {
                details += `<br><em>${data.note}</em><br><br>`;
            }
            details += `Message: ${escapeHTML(data.message)}`;

            if (data.task_id) {
                details += `<br><small>Task ID: ${data.task_id}</small>`;
            }

            resultDiv.innerHTML = details;
            closeDispatchModal();

            // Refresh zones and alerts after a successful dispatch
            if (data.status === 'dispatched') {
                fetchZones();
                fetchAlertsFeed();
                showToast('Alert dispatched successfully', 'success');
            }
        } else {
            resultDiv.className = 'alert alert-error';
            resultDiv.textContent = data.error || 'Failed to dispatch alert';
            showToast('Dispatch failed', 'error');
        }
    })
    .catch(err => {
        console.error(err);
        showToast('Network error during dispatch', 'error');
    });
});

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
