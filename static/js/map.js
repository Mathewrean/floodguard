const NAIROBI = [-1.2921, 36.8219];
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

function zoneColour(score) {
    if (score > 0.7) return '#C0392B';   // High risk: red
    if (score > 0.4) return '#E67E22';   // Moderate: orange
    return '#27AE60';                      // Safe: green
}

function zoneStyle(score, isHovered = false) {
    const baseColor = zoneColour(score);
    // High-contrast borders + semi-transparent fill for legibility
    return {
        color: isHovered ? '#ffffff' : baseColor,        // white border on hover, else risk color
        weight: isHovered ? 4 : 3,                     // thicker border when hovered
        fillColor: baseColor,
        fillOpacity: isHovered ? 0.25 : 0.12,          // slightly stronger fill on hover
        // Dash array for overlapping zones: high-risk gets solid, moderate dashed, safe dotted
        dashArray: score > 0.7 ? null : (score > 0.4 ? '8, 4' : '2, 4'),
        className: 'zone-polygon'
    };
}

function zoneStatus(score) {
    if (score > 0.7) return 'HIGH RISK';
    if (score > 0.4) return 'MODERATE';
    return 'SAFE';
}

function createBaseMap(elementId, zoom = 12) {
    const element = document.getElementById(elementId);
    if (!element || typeof L === 'undefined') return null;
    if (element._leaflet_id) return null;

    // Start with a neutral view, will be updated by locateUser
    const map = L.map(elementId).setView([0, 0], zoom);
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
    const shouldFitBounds = options.fitBounds !== false;
    const layer = L.layerGroup().addTo(map);
    const bounds = [];
    let zonesLayerGroup = L.featureGroup();

    try {
        const data = await fetch('/api/v1/zones/?limit=500').then(r => r.json());
        const zones = Array.isArray(data) ? data : (data.results || []);

        if (!zones.length) {
            showMapNotice(map, 'No flood zones configured yet. Add zones in Django Admin to enable polygon overlays.');
            return layer;
        }

        zones.forEach(zone => {
            const score = Number(zone.risk_score || 0);
            const geoLayer = L.geoJSON(zone.polygon, {
                style: function(feature) {
                    return zoneStyle(score, false);
                }
            }).bindPopup(`
                <strong>${escapeHTML(zone.name)}</strong><br>
                Risk Score: ${(score * 100).toFixed(0)}%<br>
                Status: ${zoneStatus(score)}
            `);

            geoLayer.riskScore = score;
            geoLayer.originalStyle = zoneStyle(score, false);

            // Hover: bring to front and dim others
            geoLayer.on('mouseover', function() {
                this.setStyle(zoneStyle(score, true));
                this.bringToFront();
                zonesLayerGroup.eachLayer(other => {
                    if (other !== geoLayer && other.setStyle) {
                        other.setStyle({ fillOpacity: 0.06, weight: 1 });
                    }
                });
            });
            geoLayer.on('mouseout', function() {
                this.setStyle(this.originalStyle);
                zonesLayerGroup.eachLayer(other => {
                    if (other.setStyle && other.originalStyle) {
                        other.setStyle(other.originalStyle);
                    }
                });
            });

            geoLayer.addTo(layer);
            zonesLayerGroup.addLayer(geoLayer);
            geoLayer.eachLayer(item => bounds.push(item.getBounds ? item.getBounds() : null));
        });

        const realBounds = bounds.filter(Boolean);
        if (shouldFitBounds && realBounds.length) {
            const group = L.featureGroup(realBounds.map(bound => L.rectangle(bound, { opacity: 0, fillOpacity: 0 })));
            map.fitBounds(group.getBounds(), { padding: [28, 28] });
        }
    } catch (error) {
        console.error('Error loading zones:', error);
        showMapNotice(map, 'Zone overlays are temporarily unavailable. Basemap remains active.');
    }

    return layer;
}

async function renderReadings(map) {
    const layer = L.layerGroup().addTo(map);
    try {
        const data = await fetch('/api/v1/readings/').then(r => r.json());
        const readings = Array.isArray(data) ? data : (data.results || []);
        if (!readings.length) return layer;
        readings.forEach(reading => {
            if (!reading.location) return;
            const score = Number(reading.risk_score || 0);
            const marker = L.circleMarker([reading.location[1], reading.location[0]], {
                radius: 7,
                color: '#fff',
                weight: 2,
                fillColor: zoneColour(score),
                fillOpacity: 0.9
            }).bindPopup(`
                <strong>Flood Reading</strong><br>
                Water level: ${reading.water_level_metres}m<br>
                Risk Score: ${(score * 100).toFixed(0)}%
            `);
            marker.addTo(layer);
        });
    } catch (error) {
        console.error('Error loading readings:', error);
    }
    return layer;
}

// Update the top metrics bar with aggregated data
async function updateMetricsBar() {
    try {
        const [zonesRes, readingsRes, statsRes] = await Promise.all([
            fetch('/api/v1/zones/?limit=500').then(r => r.json()),
            fetch('/api/v1/readings/?limit=1000').then(r => r.json()),
            fetch('/api/v1/stats/').then(r => r.json())
        ]);

        const zones = Array.isArray(zonesRes) ? zonesRes : (zonesRes.results || []);
        const readings = Array.isArray(readingsRes) ? readingsRes : (readingsRes.results || []);
        const stats = statsRes; // plain object

        // Compute max risk from zones
        const maxRisk = zones.length
            ? Math.max(...zones.map(z => Number(z.risk_score) || 0))
            : 0;

        // Compute average water level from readings
        const validReadings = readings.filter(r => r.water_level_metres != null);
        const avgLevel = validReadings.length
            ? (validReadings.reduce((sum, r) => sum + Number(r.water_level_metres), 0) / validReadings.length)
            : null;

        // Alerts today (as rate indicator)
        const alertsToday = stats.alerts_today || 0;

        // Update DOM with high-contrast values
        const riskEl = document.getElementById('metric-risk');
        const levelEl = document.getElementById('metric-levels');
        const rateEl = document.getElementById('metric-rate');

        if (riskEl) riskEl.textContent = `${(maxRisk * 100).toFixed(0)}%`;
        if (levelEl) levelEl.textContent = avgLevel !== null ? avgLevel.toFixed(2) : '--';
        if (rateEl) rateEl.textContent = alertsToday;

    } catch (error) {
        console.error('Failed to update metrics bar:', error);
    }
}

function locateUser(map) {
    return new Promise((resolve) => {
        if (navigator.geolocation) {
            let resolved = false;
            let marker = null;

            const acceptPosition = pos => {
                const { latitude, longitude } = pos.coords;
                const latLng = [latitude, longitude];
                if (!marker) {
                    marker = L.marker(latLng, {
                        icon: L.divIcon({
                            className: 'user-marker',
                            html: '📍',
                            iconSize: [24, 24]
                        })
                    }).bindPopup('Your Location').addTo(map);
                } else {
                    marker.setLatLng(latLng);
                }
                map.setView(latLng, Math.max(map.getZoom(), 15), { animate: true });
                window._lastKnownPosition = { lat: latitude, lng: longitude, accuracy: pos.coords.accuracy };
                if (!resolved) {
                    resolved = true;
                    resolve(latLng);
                }
            };

            const watchId = navigator.geolocation.watchPosition(acceptPosition, (error) => {
                console.warn('Geolocation failed:', error.message);
                if (!resolved) {
                    resolved = true;
                    map.setView(NAIROBI, 12);
                    resolve(NAIROBI);
                }
            }, {
                enableHighAccuracy: true,
                timeout: 20000,
                maximumAge: 0
            });

            setTimeout(() => {
                if (!resolved) {
                    resolved = true;
                    resolve(window._lastKnownPosition ? [window._lastKnownPosition.lat, window._lastKnownPosition.lng] : map.getCenter());
                }
            }, 2500);

            window.addEventListener('beforeunload', () => navigator.geolocation.clearWatch(watchId), { once: true });
        } else {
            console.warn('Geolocation not supported');
            map.setView(NAIROBI, 12);
            resolve(NAIROBI);
        }
    });
}

async function initMapPreview() {
    const map = createBaseMap('map-preview', 11);
    if (!map) return;

    renderZones(map, { fitBounds: true });
    locateUser(map);
}

async function initFullMap() {
    const map = createBaseMap('map', 12);
    if (!map) return;

    const userLocation = await locateUser(map);
    const zonesLayer = await renderZones(map, { fitBounds: !userLocation });
    const readingsLayer = await renderReadings(map);

    // Update metrics bar (Levels, Rate, Risk)
    updateMetricsBar();
    // Refresh metrics every 30 seconds
    setInterval(updateMetricsBar, 30000);

    const zonesToggle = document.getElementById('toggle-zones');
    const readingsToggle = document.getElementById('toggle-readings');
    if (zonesToggle) {
        zonesToggle.addEventListener('change', () => {
            zonesToggle.checked ? zonesLayer.addTo(map) : map.removeLayer(zonesLayer);
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
