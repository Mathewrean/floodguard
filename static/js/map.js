const NAIROBI = [-1.2921, 36.8219];

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

function createBaseMap(elementId, zoom = 12) {
    const element = document.getElementById(elementId);
    if (!element || typeof L === 'undefined') return null;
    if (element._leaflet_id) return null;

    const map = L.map(elementId).setView(NAIROBI, zoom);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors'
    }).addTo(map);
    return map;
}

async function renderZones(map) {
    const layer = L.layerGroup().addTo(map);
    const bounds = [];

    try {
        const data = await fetch('/api/v1/zones/').then(r => r.json());
        const zones = Array.isArray(data) ? data : (data.results || []);

        zones.forEach(zone => {
            const score = Number(zone.risk_score || 0);
            const colour = zoneColour(score);
            const geoLayer = L.geoJSON(zone.polygon, {
                style: {
                    color: colour,
                    fillColor: colour,
                    fillOpacity: 0.25,
                    weight: 2
                }
            }).bindPopup(`
                <strong>${zone.name}</strong><br>
                Risk Score: ${(score * 100).toFixed(0)}%<br>
                Status: ${zoneStatus(score)}
            `);
            geoLayer.addTo(layer);
            geoLayer.eachLayer(item => bounds.push(item.getBounds ? item.getBounds() : null));
        });

        const realBounds = bounds.filter(Boolean);
        if (realBounds.length) {
            const group = L.featureGroup(realBounds.map(bound => L.rectangle(bound, { opacity: 0, fillOpacity: 0 })));
            map.fitBounds(group.getBounds(), { padding: [28, 28] });
        }
    } catch (error) {
        console.error('Error loading zones:', error);
    }

    return layer;
}

async function renderReadings(map) {
    const layer = L.layerGroup().addTo(map);
    try {
        const data = await fetch('/api/v1/readings/').then(r => r.json());
        const readings = Array.isArray(data) ? data : (data.results || []);
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

function locateUser(map) {
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(pos => {
            const { latitude, longitude } = pos.coords;
            L.marker([latitude, longitude], {
                icon: L.divIcon({
                    className: 'user-marker',
                    html: '📍',
                    iconSize: [24, 24]
                })
            }).bindPopup('Your Location').addTo(map);
            map.setView([latitude, longitude], 13);
        }, () => {
            map.setView(NAIROBI, 12);
        });
    } else {
        map.setView(NAIROBI, 12);
    }
}

async function initMapPreview() {
    const map = createBaseMap('map-preview', 11);
    if (!map) return;
    await renderZones(map);
}

async function initFullMap() {
    const map = createBaseMap('map', 12);
    if (!map) return;

    const zonesLayer = await renderZones(map);
    const readingsLayer = await renderReadings(map);
    locateUser(map);

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
