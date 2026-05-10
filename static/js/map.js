const NAIROBI = { lat: -1.2921, lng: 36.8219 };
const NAIROBI_LATLNG = [NAIROBI.lat, NAIROBI.lng];

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

function safeHTML(value) {
    if (window.escapeHTML) return window.escapeHTML(value);
    const template = document.createElement('template');
    template.textContent = value == null ? '' : String(value);
    return template.innerHTML;
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

function timeAgo(ts) {
    if (!ts) return 'unknown';
    const diff = Math.floor((Date.now() - new Date(ts)) / 1000);
    if (Number.isNaN(diff)) return 'unknown';
    if (diff < 60) return `${diff}s ago`;
    if (diff < 3600) return `${Math.floor(diff / 60)}m ago`;
    return `${Math.floor(diff / 3600)}h ago`;
}

function createBaseMap(elementId, zoom = 12) {
    const element = document.getElementById(elementId);
    if (!element || typeof L === 'undefined') return null;
    if (element._leaflet_id) return null;

    const map = L.map(elementId).setView(NAIROBI_LATLNG, zoom);
    addBasemap(map, 0);
    return map;
}

function addBasemap(map, index) {
    const provider = BASEMAPS[index] || BASEMAPS[0];
    const layer = L.tileLayer(provider.url, {
        ...provider.options,
        crossOrigin: true
    }).addTo(map);

    layer.on('tileerror', () => {
        if (index + 1 < BASEMAPS.length && !map._fallbackBasemapLoaded) {
            map._fallbackBasemapLoaded = true;
            map.removeLayer(layer);
            addBasemap(map, index + 1);
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

async function renderZones(map, options = {}) {
    try {
        const res = await fetch('/api/v1/zones/?limit=500');
        const data = await res.json();
        const zones = Array.isArray(data) ? data : (data.results || []);

        const dirty = ['zone', 'area', 'region', 'test', 'seed', '0,0', 'null'];
        const clean = zones.filter(z =>
            z.name && !dirty.some(d => z.name.toLowerCase().includes(d))
        );

        if (!clean.length) {
            showMapNotice(map, 'No configured flood zones yet. Live location assessment is still available.');
        }

        const zonesLayer = L.featureGroup();
        const labelsLayer = L.layerGroup();

        clean.forEach(zone => {
            if (!zone.polygon) return;

            const score = Number(zone.risk_score || 0);
            const pct = Math.round(score * 100);
            const colour = zoneColour(score);
            const severity = zoneStatus(score);

            const layer = L.geoJSON(zone.polygon, {
                style: {
                    color: colour,
                    fillColor: colour,
                    fillOpacity: score > 0.7 ? 0.30 : 0.18,
                    weight: score > 0.7 ? 3 : 2,
                    dashArray: score > 0.7 ? null : '4,4',
                    className: score > 0.7 ? 'zone-polygon high-risk-pulse' : 'zone-polygon'
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
        });

        zonesLayer.addTo(map);
        labelsLayer.addTo(map);
        zonesLayer.labelsLayer = labelsLayer;

        if (options.fitBounds && zonesLayer.getLayers().length > 0) {
            try {
                map.fitBounds(zonesLayer.getBounds(), { padding: [20, 20] });
            } catch (e) {}
        }

        return zonesLayer;
    } catch (e) {
        console.error('Failed to render zones:', e);
        showMapNotice(map, 'Zone overlays are temporarily unavailable. Basemap remains active.');
        return L.featureGroup().addTo(map);
    }
}

async function renderReadings(map) {
    const layer = L.layerGroup().addTo(map);
    try {
        const data = await fetch('/api/v1/readings/?limit=1000').then(r => r.json());
        const readings = Array.isArray(data) ? data : (data.results || []);
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

async function updateMetricsBar() {
    try {
        const [zonesRes, readingsRes, statsRes] = await Promise.all([
            fetch('/api/v1/zones/?limit=500').then(r => r.json()),
            fetch('/api/v1/readings/?limit=1000').then(r => r.json()),
            fetch('/api/v1/stats/').then(r => r.json())
        ]);

        const zones = Array.isArray(zonesRes) ? zonesRes : (zonesRes.results || []);
        const readings = Array.isArray(readingsRes) ? readingsRes : (readingsRes.results || []);
        const stats = statsRes || {};
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
        console.error('Failed to update metrics bar:', error);
    }
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
            showStatus('Nairobi (testing) - click Allow for your location', null);
            setTimeout(hideStatus, 4000);
            map.setView(NAIROBI_LATLNG, 12);
            L.circleMarker(NAIROBI_LATLNG, {
                radius: 8,
                fillColor: '#6B7A8D',
                color: '#fff',
                weight: 2,
                fillOpacity: 0.5
            })
                .bindPopup('Nairobi default - allow location for your position')
                .addTo(map);
            resolve(null);
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
                fetchLiveZoneForLocation(latitude, longitude, map);
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

async function fetchLiveZoneForLocation(lat, lon, map) {
    try {
        const res = await fetch(`/api/v1/dynamic-zone/?lat=${encodeURIComponent(lat)}&lon=${encodeURIComponent(lon)}`);
        if (!res.ok) return;
        const data = await res.json();

        if (data.live_assessment && data.risk_score !== undefined) {
            const colour = zoneColour(Number(data.risk_score || 0));
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
                            <span style="font-size:12px;color:${colour};font-weight:700">${pct}% - ${safeHTML(data.severity)}</span>
                        </div>
                        <small style="color:#6B7A8D">Live assessment - Open-Meteo</small>
                    </div>
                `)
                .openOn(map);
        }
    } catch (e) {
        console.info('Live location assessment unavailable:', e.message);
    }
}

async function initMapPreview() {
    const map = createBaseMap('map-preview', 11);
    if (!map) return;
    renderZones(map, { fitBounds: true });
}

async function initFullMap() {
    const map = createBaseMap('map', 12);
    if (!map) return;

    const userLocation = await locateUser(map);
    const zonesLayer = await renderZones(map, { fitBounds: !userLocation });
    const readingsLayer = await renderReadings(map);

    updateMetricsBar();
    setInterval(updateMetricsBar, 5000);

    const zonesToggle = document.getElementById('toggle-zones');
    const readingsToggle = document.getElementById('toggle-readings');
    if (zonesToggle) {
        zonesToggle.addEventListener('change', () => {
            zonesToggle.checked ? zonesLayer.addTo(map) : map.removeLayer(zonesLayer);
            if (zonesLayer.labelsLayer) {
                zonesToggle.checked ? zonesLayer.labelsLayer.addTo(map) : map.removeLayer(zonesLayer.labelsLayer);
            }
        });
    }
    if (readingsToggle) {
        readingsToggle.addEventListener('change', () => {
            readingsToggle.checked ? readingsLayer.addTo(map) : map.removeLayer(readingsLayer);
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
window.locateUser = locateUser;
window.zoneColour = zoneColour;
