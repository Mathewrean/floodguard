const DEFAULT_LATLNG = [0, 0];

const BASEMAPS = [
    {
        url: 'https://{s}.basemaps.cartocdn.com/rastertiles/voyager/{z}/{x}/{y}{r}.png',
        options: {
            subdomains: 'abcd',
            maxZoom: 20,
            attribution: '&copy; OpenStreetMap contributors &copy; CARTO'
        }
    },
    {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        options: {
            maxZoom: 19,
            attribution: 'Tiles &copy; Esri'
        }
    }
];

const ENGLISH_BASEMAPS = [
    {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}',
        options: {
            maxZoom: 19,
            attribution: 'Tiles &copy; Esri'
        }
    },
    {
        url: 'https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}',
        options: {
            maxZoom: 19,
            attribution: 'Tiles &copy; Esri'
        }
    }
];

let mapInstance = null;
let zonesCache = null;
let readingsCache = null;
let statsCache = null;
let currentZonesLayer = null;
let currentReadingsLayer = null;
let userMarker = null;

// Updates the metrics bar from cached data when all required caches are populated
function updateMetricsBarIfReady() {
    if (!zonesCache || !readingsCache || !statsCache) return;

    try {
        const zones = zonesCache;
        const readings = readingsCache;
        const stats = statsCache;

        const maxRisk = zones.length ? Math.max(...zones.map(z => Number(z.risk_score) || 0)) : 0;
        const validReadings = readings.filter(r => r.water_level_metres != null);
        const avgLevel = validReadings.length
            ? (validReadings.reduce((sum, r) => sum + Number(r.water_level_metres), 0) / validReadings.length)
            : null;

        const riskEl = document.getElementById('metric-risk');
        const levelEl = document.getElementById('metric-levels');
        const rateEl = document.getElementById('metric-rate');

        if (riskEl) riskEl.textContent = `${(maxRisk * 100).toFixed(0)}%`;
        if (levelEl) levelEl.textContent = avgLevel !== null ? avgLevel.toFixed(2) : '--';
        if (rateEl) rateEl.textContent = stats.alerts_today || 0;
    } catch (error) {
        console.error('Failed to update metrics bar from cache:', error);
    }
}

// Polls and caches zones, updates map layer every 60s
async function fetchZones(options = {}) {
    try {
        const data = await apiData('/api/v1/zones/');
        const zones = Array.isArray(data) ? data : (data.results || []);

        if (currentZonesLayer) {
            currentZonesLayer.remove();
            if (currentZonesLayer.labelsLayer) currentZonesLayer.labelsLayer.remove();
        }

        currentZonesLayer = renderZones(mapInstance, zones, options);
        zonesCache = zones;
        updateMetricsBarIfReady();
    } catch (error) {
        console.error('Error fetching zones:', error);
    }
}

// Polls and caches readings, updates map layer every 60s
async function fetchReadings() {
    try {
        const data = await apiData('/api/v1/readings/');
        const readings = Array.isArray(data) ? data : (data.results || []);

        if (currentReadingsLayer) currentReadingsLayer.remove();
        currentReadingsLayer = renderReadings(mapInstance, readings);
        readingsCache = readings;
        updateMetricsBarIfReady();
    } catch (error) {
        console.error('Error fetching readings:', error);
    }
}

// Polls and caches stats every 30s
async function fetchStats() {
    try {
        const data = await apiData('/api/v1/stats/');
        statsCache = data || {};
        updateMetricsBarIfReady();
    } catch (error) {
        console.error('Error fetching stats:', error);
    }
}

function safeHTML(value) {
    if (window.escapeHTML) return window.escapeHTML(value);
    const template = document.createElement('template');
    template.textContent = value == null ? '' : String(value);
    return template.innerHTML;
}

async function apiData(url) {
    // Delegate to global cachedFetch (which now applies tiered TTLs)
    if (typeof window.cachedFetch === 'function') {
        return window.cachedFetch(url);
    }
    // Fallback if main.js hasn’t loaded yet
    const response = await fetch(url);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return response.json();
}

function zoneColour(score) {
    return getRiskBand(score).colour;
}

function zoneStatus(score) {
    return getRiskBand(score).label;
}

function timeAgo(ts) {
    if (!ts) return 'unknown';
    const diff = Math.floor((Date.now() - new Date(ts)) / 1000);
    if (Number.isNaN(diff)) return 'unknown';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}

function createBaseMap(elementId, zoom = 12, useEnglish = false) {
    const element = document.getElementById(elementId);
    if (!element || typeof L === 'undefined') return null;
    if (element._leaflet_id) return null;

    const provider = useEnglish ? ENGLISH_BASEMAPS[0] : BASEMAPS[0];
    const map = L.map(elementId).setView(DEFAULT_LATLNG, zoom);
    addBasemap(map, 0, useEnglish);
    return map;
}

function defaultLocation() {
    return { ...DEFAULT_LOCATION };
}

function addBasemap(map, index, useEnglish = false) {
    const basemaps = useEnglish ? ENGLISH_BASEMAPS : BASEMAPS;
    const provider = basemaps[index] || basemaps[0];
    const layer = L.tileLayer(provider.url, {
        ...provider.options,
        crossOrigin: true
    }).addTo(map);

    layer.on('tileerror', () => {
        if (index + 1 < basemaps.length && !map._fallbackBasemapLoaded) {
            map._fallbackBasemapLoaded = true;
            map.removeLayer(layer);
            addBasemap(map, index + 1, useEnglish);
        }
    });
}

function showMapNotice(map, message) {
    const notice = L.control({ position: 'bottomleft' });
    notice.onAdd = function() {
        const div = L.DomUtil.create('div', 'map-empty-state');
        div.textContent = message;
        return div;
    };
    notice.addTo(map);
    return notice;
}

function showBanner(message, colour) {
    let banner = document.getElementById('risk-banner');
    if (!banner) {
        banner = document.createElement('div');
        banner.id = 'risk-banner';
        banner.className = 'risk-banner';
        document.body.appendChild(banner);
    }
    banner.textContent = message;
    banner.style.background = colour;
    banner.style.borderColor = colour;
    banner.style.display = 'block';
    clearTimeout(banner._hideTimer);
    banner._hideTimer = setTimeout(() => {
        banner.style.display = 'none';
    }, 7000);
}

function openSafeRoutePanel() {
    const panel = document.querySelector('.safe-route-page .safe-route-panel');
    if (panel) {
        panel.scrollIntoView({ behavior: 'smooth', block: 'start' });
        panel.classList.add('focus');
        return;
    }
    window.location.href = '/safe-route/';
}

function renderZones(map, zones, options = {}) {
    if (!map || !zones) return L.featureGroup().addTo(map);

    const shouldFitBounds = options.fitBounds !== false;
    const zonesLayer = L.featureGroup();
    const labelsLayer = L.layerGroup();
    const bounds = [];

    zones.forEach(zone => {
        if (!zone.polygon) return;

        const score = Number(zone.risk_score || 0);
        const band = getRiskBand(score);
        const colour = band.colour;
        const severity = band.label;
        const pct = Math.round(score * 100);

        const layer = L.geoJSON(zone.polygon, {
            style: {
                color: colour,
                fillColor: colour,
                fillOpacity: score >= 0.85 ? 0.30 : score >= 0.7 ? 0.24 : 0.18,
                weight: score >= 0.7 ? 3 : 2,
                dashArray: score >= 0.7 ? null : '4,4',
                className: score >= 0.7 ? 'zone-polygon high-risk-pulse' : 'zone-polygon'
            }
        });

        const popup = `
            <div style="min-width:220px;font-family:-apple-system,Arial,sans-serif">
                <div style="background:${colour};padding:10px 14px;border-radius:8px 8px 0 0;display:flex;justify-content:space-between;align-items:center">
                    <strong style="font-size:15px;color:white">${safeHTML(zone.name)}</strong>
                    <span style="background:rgba(255,255,255,0.25);color:white;padding:2px 8px;border-radius:10px;font-size:11px;font-weight:700">${severity}</span>
                </div>
                <div style="padding:12px 14px;background:white;border-radius:0 0 8px 8px">
                    <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px">
                        <div style="flex:1;background:#eee;border-radius:3px;height:6px">
                            <div style="background:${colour};width:${pct}%;height:6px;border-radius:3px;transition:width 0.5s"></div>
                        </div>
                        <span style="font-weight:700;color:${colour};font-size:14px">${pct}%</span>
                    </div>
                    <div style="font-size:12px;color:#6B7A8D;display:flex;justify-content:space-between">
                        <span>Threshold: ${Math.round(Number(zone.risk_threshold || 0.65) * 100)}%</span>
                        <span>Updated: ${timeAgo(zone.updated_at)}</span>
                    </div>
                </div>
            </div>`;

        layer.bindPopup(popup, { maxWidth: 280 });
        layer.addTo(zonesLayer);

        if (zone.centroid) {
            const centroidLatLng = Array.isArray(zone.centroid)
                ? [zone.centroid[1], zone.centroid[0]]
                : [zone.centroid.lat, zone.centroid.lng];

            L.tooltip({
                permanent: true,
                direction: 'center',
                className: 'zone-label'
            })
                .setLatLng(centroidLatLng)
                .setContent(`<span style="font-weight:700;font-size:12px;color:${colour}">${safeHTML(zone.name)}</span>`)
                .addTo(labelsLayer);
        }

        if (zone.polygon) {
            try {
                const geoJSON = zone.polygon;
                if (geoJSON.coordinates) {
                    const coords = geoJSON.coordinates[0];
                    coords.forEach(coord => bounds.push([coord[1], coord[0]]));
                }
            } catch(e){}
        }
    });

    zonesLayer.addTo(map);
    labelsLayer.addTo(map);
    zonesLayer.labelsLayer = labelsLayer;

    if (shouldFitBounds && bounds.length) {
        try {
            map.fitBounds(bounds, { padding: [20, 20] });
        } catch (e) {}
    }

    return zonesLayer;
}

function renderReadings(map, readings) {
    const layer = L.layerGroup().addTo(map);
    try {
        readings.forEach(reading => {
            if (!reading.location) return;
            const score = Number(reading.risk_score || 0);
            L.circleMarker([reading.location[1], reading.location[0]], {
                radius: 7,
                color: '#fff',
                weight: 2,
                fillColor: zoneColour(score),
                fillOpacity: 0.9
            }).bindPopup(`
                <strong>Flood Reading</strong><br>
                Water level: ${safeHTML(reading.water_level_metres)}m<br>
                Risk Score: ${(score * 100).toFixed(0)}%
            `).addTo(layer);
        });
    } catch (error) {
        console.error('Error loading readings:', error);
    }
    return layer;
}

function locateUser(map) {
    return new Promise((resolve) => {
        const statusEl = document.getElementById('location-status');
        const showStatus = (msg, colour) => {
            if (!statusEl) return;
            statusEl.textContent = msg;
            statusEl.style.background = colour || 'rgba(13,46,82,0.9)';
            statusEl.style.display = 'block';
        };
        const hideStatus = () => {
            if (statusEl) statusEl.style.display = 'none';
        };

        const useFallback = (reason) => {
            console.info('Location fallback:', reason);
            map.setView(DEFAULT_LATLNG, 12);
            showStatus('Using default global view.', null);
            setTimeout(hideStatus, 4000);
            resolve({ ...DEFAULT_LOCATION, source: 'default' });
        };

        if (!('geolocation' in navigator)) {
            useFallback('API unavailable');
            return;
        }

        showStatus('Detecting your location...', null);

        navigator.geolocation.getCurrentPosition(
            (pos) => {
                const { latitude, longitude, accuracy } = pos.coords;

                if (!latitude || !longitude || latitude === 0 || longitude === 0) {
                    useFallback('Invalid coordinates received');
                    return;
                }

                const latLng = [latitude, longitude];
                hideStatus();

                L.circleMarker(latLng, {
                    radius: 10,
                    fillColor: '#2E75B6',
                    color: '#fff',
                    weight: 3,
                    fillOpacity: 0.9,
                    zIndexOffset: 1000
                })
                    .bindPopup(`Your Location<br><small>Accuracy: +/-${Math.round(accuracy)}m</small>`)
                    .addTo(map);

                if (accuracy < 2000) {
                    L.circle(latLng, {
                        radius: accuracy,
                        color: '#2E75B6',
                        fillOpacity: 0.05,
                        weight: 1
                    }).addTo(map);
                }

                map.setView(latLng, accuracy < 500 ? 15 : 13);
                fetchLiveZoneForLocation(latitude, longitude, map, accuracy);
                resolve(latLng);
            },
            (err) => {
                const reasons = {
                    1: 'Permission denied',
                    2: 'Position unavailable',
                    3: 'Timed out'
                };
                useFallback(reasons[err.code] || 'Unknown error');
            },
            {
                enableHighAccuracy: true,
                timeout: 8000,
                maximumAge: 60000
            }
        );
    });
}

async function fetchLiveZoneForLocation(lat, lon, map, accuracy = null) {
    try {
        const payload = { lat, lon, accuracy };
        const res = await fetch('/api/v1/dynamic-zone/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': typeof getCookie === 'function' ? getCookie('csrftoken') : ''
            },
            body: JSON.stringify(payload)
        });
        if (!res.ok) return;
        const data = await res.json();

        if (data.has_zone) {
            const zone = Array.isArray(data.zones) && data.zones.length
                ? [...data.zones].sort((a, b) => Number(b.risk_score || 0) - Number(a.risk_score || 0))[0]
                : {
                    id: data.zone_id,
                    name: data.zone_name,
                    risk_score: data.risk_score,
                    risk_threshold: data.risk_threshold
                };
            const score = Number(zone.risk_score || 0);
            const band = getRiskBand(score);
            const colour = band.colour;

            L.popup({ className: 'live-zone-popup' })
                .setLatLng([lat, lon])
                .setContent(`
                    <div style="min-width:180px">
                        <strong style="color:${colour}">${safeHTML(zone.name)}</strong>
                        <div style="margin:6px 0">
                            <span style="font-size:12px;color:${colour};font-weight:700">${band.label} - ${(score * 100).toFixed(0)}%</span>
                        </div>
                        <small style="color:#6B7A8D">${data.created_zone ? 'Live zone created from your GPS area.' : 'You are inside a mapped flood zone.'}</small>
                    </div>
                `)
                .openOn(map);
            if (score >= 0.7) {
                showBanner(`⚠ You are in ${safeHTML(zone.name)} — ${band.label}`, band.colour);
            }
            if (score >= 0.85) {
                openSafeRoutePanel();
            }
            return;
        }

        if (data.live_assessment && data.risk_score !== undefined) {
            const band = getRiskBand(Number(data.risk_score || 0));
            const colour = band.colour;
            const pct = Math.round(Number(data.risk_score || 0) * 100);

            L.popup({ className: 'live-zone-popup' })
                .setLatLng([lat, lon])
                .setContent(`
                    <div style="min-width:180px">
                        <strong style="color:${colour}">${safeHTML(data.zone_name)}</strong>
                        <div style="margin:6px 0">
                            <div style="background:#eee;border-radius:4px;height:6px">
                                <div style="background:${colour};width:${pct}%;height:6px;border-radius:4px"></div>
                            </div>
                            <span style="font-size:12px;color:${colour};font-weight:700">${pct}% - ${safeHTML(data.severity || band.label)}</span>
                        </div>
                        <small style="color:#6B7A8D">Live assessment from FloodGuard sources</small>
                    </div>
                `)
                .openOn(map);
        }
    } catch (e) {
        console.info('Live location assessment unavailable:', e.message);
    }
}

async function initMapPreview() {
    const map = createBaseMap('map-preview', 11, true);
    if (!map) return;
    try {
        const data = await apiData('/api/v1/zones/');
        const zones = Array.isArray(data) ? data : (data.results || []);
        renderZones(map, zones, { fitBounds: true });
    } catch (error) {
        console.error('Failed to load zones for preview:', error);
    }
}

async function initFullMap() {
    const map = createBaseMap('map', 12, true);
    if (!map) return;
    mapInstance = map;

    FloodLocation.on((loc, isReal) => {
        map.setView([loc.lat, loc.lon], loc.zoom || 12);
        if (userMarker) map.removeLayer(userMarker);
        userMarker = L.circleMarker([loc.lat, loc.lon], {
            radius: 10,
            fillColor: isReal ? '#2E75B6' : '#94A3B8',
            color: '#fff',
            weight: 3,
            fillOpacity: 0.9,
            zIndexOffset: 1000
        }).bindPopup(isReal ? `Your Location<br><small>Accuracy: +/-${Math.round(loc.accuracy || 0)}m</small>` : '📍 Default Location').addTo(map);
    });
    FloodLocation.detect('auto');

    await Promise.all([fetchZones(), fetchReadings()]);
    await fetchStats();

    setInterval(fetchZones, 60000);
    setInterval(fetchReadings, 60000);
    setInterval(fetchStats, 30000);

    const zonesToggle = document.getElementById('toggle-zones');
    const readingsToggle = document.getElementById('toggle-readings');
    if (zonesToggle) {
        zonesToggle.addEventListener('change', () => {
            if (currentZonesLayer) {
                zonesToggle.checked ? currentZonesLayer.addTo(mapInstance) : mapInstance.removeLayer(currentZonesLayer);
                if (currentZonesLayer.labelsLayer) {
                    zonesToggle.checked ? currentZonesLayer.labelsLayer.addTo(mapInstance) : mapInstance.removeLayer(currentZonesLayer.labelsLayer);
                }
            }
        });
    }
    if (readingsToggle) {
        readingsToggle.addEventListener('change', () => {
            if (currentReadingsLayer) {
                readingsToggle.checked ? currentReadingsLayer.addTo(mapInstance) : mapInstance.removeLayer(currentReadingsLayer);
            }
        });
    }
}

document.addEventListener('DOMContentLoaded', function() {
    initMapPreview();
    initFullMap();
});

window.initMapPreview = initMapPreview;
window.initFullMap = initFullMap;
window.createBaseMap = createBaseMap;
window.renderZones = renderZones;
window.renderReadings = renderReadings;
window.zoneColour = zoneColour;
