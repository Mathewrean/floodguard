// FloodGuard GIS Dashboard - H3-based Dynamic Risk Zoning
// Implements modern GIS flood intelligence with location search and safe route integration

const RISK_COLORS = {
    high: { color: '#FF0000', opacity: 0.45 },
    medium: { color: '#FFA500', opacity: 0.35 },
    low: { color: '#FFFF00', opacity: 0.25 },
    safe: { color: '#22c55e', opacity: 0.25 },
};

const RISKS = [
    { threshold: 0.85, label: 'HIGH', level: 'high', color: '#FF0000' },
    { threshold: 0.70, label: 'MEDIUM', level: 'medium', color: '#FFA500' },
    { threshold: 0.40, label: 'LOW', level: 'low', color: '#FFFF00' },
    { threshold: 0.0, label: 'SAFE', level: 'safe', color: '#22c55e' },
];

function getRiskInfo(score) {
    const num = Number(score) || 0;
    for (const risk of RISKS) {
        if (num >= risk.threshold) return risk;
    }
    return RISKS[RISKS.length - 1];
}

let gisMap = null;
let h3Layer = null;
let userMarker = null;
let selectedCell = null;
let layerVisibility = {
    flood: true,
    satellite: false,
};
let searchMarkers = [];

// Initialize the GIS dashboard
async function initGisDashboard() {
    const mapEl = document.getElementById('gis-map');
    if (!mapEl || typeof L === 'undefined') return;

    gisMap = L.map('gis-map', {
        center: [0, 0],
        zoom: 2,
        minZoom: 2,
        maxZoom: 19,
    });

    // Add base layer (OpenStreetMap)
    const osmLayer = L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; OpenStreetMap contributors',
        maxZoom: 19,
    }).addTo(gisMap);

    // Add satellite layer
    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 19,
    });

    // Layer control
    const baseLayers = { 'Street Map': osmLayer, 'Satellite': satelliteLayer };
    L.control.layers(baseLayers, {}, { position: 'topright' }).addTo(gisMap);

    // Bind UI events
    bindGisControls();

    // Load initial H3 cells
    await loadH3Cells();

    // Start viewport-based loading
    gisMap.on('moveend', debounceLoadH3Cells);
}

function bindGisControls() {
    const searchInput = document.getElementById('gis-search-input');
    const searchBtn = document.getElementById('gis-search-btn');
    const locationBtn = document.getElementById('gis-location-btn');
    const routeBtn = document.getElementById('gis-safe-route-btn');
    const toggleBtn = document.getElementById('gis-panel-toggle');

    if (searchBtn) searchBtn.addEventListener('click', doLocationSearch);
    if (searchInput) searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doLocationSearch(); });
    if (locationBtn) locationBtn.addEventListener('click', useMyLocation);
    if (routeBtn) routeBtn.addEventListener('click', openRouteMode);
    if (toggleBtn) toggleBtn.addEventListener('click', togglePanel);

    // Layer toggles
    const floodToggle = document.getElementById('layer-flood');
    const satelliteToggle = document.getElementById('layer-satellite');
    if (floodToggle) floodToggle.addEventListener('change', e => {
        layerVisibility.flood = e.target.checked;
        if (h3Layer) {
            layerVisibility.flood ? gisMap.addLayer(h3Layer) : gisMap.removeLayer(h3Layer);
        }
    });
    if (satelliteToggle) satelliteToggle.addEventListener('change', e => {
        layerVisibility.satellite = e.target.checked;
    });
}

function togglePanel() {
    const panel = document.getElementById('gis-panel');
    if (panel) panel.classList.toggle('open');
}

async function loadH3Cells() {
    if (!gisMap) return;

    const bounds = gisMap.getBounds();
    const bbox = `${bounds.getSouthWest().lat},${bounds.getSouthWest().lng},${bounds.getNorthEast().lat},${bounds.getNorthEast().lng}`;
    const resolution = gisMap.getZoom() >= 12 ? 7 : 5;

    try {
        const data = await cachedFetch(`/api/v1/h3-cells/?min_lat=${bounds.getSouthWest().lat}&min_lon=${bounds.getSouthWest().lng}&max_lat=${bounds.getNorthEast().lat}&max_lon=${bounds.getNorthEast().lng}&resolution=${resolution}`);

        if (h3Layer) h3Layer.remove();
        h3Layer = L.layerGroup();

        const features = data.cells || [];
        for (const cell of features) {
            const risk = Number(cell.properties?.risk_score || 0);
            const riskInfo = getRiskInfo(risk);

            const polygon = L.geoJSON(cell, {
                style: {
                    fillColor: riskInfo.color,
                    fillOpacity: riskInfo.level === 'high' ? 0.45 : riskInfo.level === 'medium' ? 0.35 : 0.25,
                    color: riskInfo.color,
                    weight: 1,
                    opacity: 0.6,
                }
            }).bindPopup(createH3Popup(cell));

            polygon.addTo(h3Layer);
        }

        h3Layer.addTo(gisMap);
    } catch (e) {
        console.warn('Failed to load H3 cells:', e);
    }
}

function createH3Popup(cell) {
    const props = cell.properties || {};
    const risk = Number(props.risk_score || 0);
    const riskInfo = getRiskInfo(risk);

    return `
        <div style="min-width:200px;font-family:-apple-system,Arial,sans-serif">
            <div style="background:${riskInfo.color};padding:8px 12px;border-radius:6px 6px 0 0">
                <strong style="color:white;font-size:14px">Flood Risk Cell</strong>
            </div>
            <div style="padding:10px 12px;background:white">
                <div style="font-size:13px;margin-bottom:6px">
                    <span style="color:${riskInfo.color};font-weight:700">${riskInfo.label}</span>
                    <span style="margin-left:8px">${(risk * 100).toFixed(0)}% risk</span>
                </div>
                <div style="font-size:12px;color:#6B7A8D">
                    <div>H3: ${props.h3_index || 'N/A'}</div>
                    <div>Cells update independently based on live data</div>
                </div>
                <div style="margin-top:8px">
                    <button onclick="findSafeRouteFromCell('${props.h3_index}')" class="btn btn-sm btn-primary" style="width:100%">Find Safe Route</button>
                </div>
            </div>
        </div>
    `;
}

async function doLocationSearch() {
    const input = document.getElementById('gis-search-input');
    if (!input) return;

    const query = input.value.trim();
    if (!query) return;

    try {
        const data = await cachedFetch(`/api/v1/geocode/?q=${encodeURIComponent(query)}`);
        const results = data.results || [];

        if (results.length) {
            clearSearchMarkers();
            const result = results[0];
            const latlng = [result.lat, result.lon];

            // Add marker
            const marker = L.marker(latlng).addTo(gisMap);
            marker.bindPopup(`<strong>${result.display_name}</strong>`).openPopup();
            searchMarkers.push(marker);

            // Pan to location
            gisMap.setView(latlng, 13);

            // Load nearby emergency services
            showNearbyEmergencyServices(result.lat, result.lon);
        } else {
            showError('Location not found. Try a city name, address, or coordinates (lat,lon).');
        }
    } catch (e) {
        showError('Search failed. Please try again.');
    }
}

function clearSearchMarkers() {
    searchMarkers.forEach(m => m.remove());
    searchMarkers = [];
}

async function useMyLocation() {
    if (!navigator.geolocation) {
        showError('Geolocation not supported.');
        return;
    }

    const btn = document.getElementById('gis-location-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Locating...';
    }

    try {
        const pos = await new Promise((resolve, reject) => {
            navigator.geolocation.getCurrentPosition(resolve, reject, {
                enableHighAccuracy: true,
                timeout: 10000,
                maximumAge: 60000,
            });
        });

        const { latitude, longitude, accuracy } = pos.coords;
        const latlng = [latitude, longitude];

        // Add pulsing user marker
        if (userMarker) userMarker.remove();
        userMarker = L.marker(latlng, {
            icon: L.divIcon({
                className: 'pulse-marker',
                html: '',
                iconSize: [20, 20],
                iconAnchor: [10, 10],
            }),
        }).addTo(gisMap);

        gisMap.setView(latlng, accuracy < 500 ? 15 : 13);

        // Check risk at user location
        checkLocationRisk(latitude, longitude);

        // Show nearby emergency services
        showNearbyEmergencyServices(latitude, longitude);
    } catch (e) {
        showError('Unable to get location: ' + e.message);
    } finally {
        if (btn) {
            btn.disabled = false;
            btn.textContent = 'My Location';
        }
    }
}

async function checkLocationRisk(lat, lon) {
    try {
        const data = await cachedFetch(`/api/v1/dynamic-zone/?lat=${lat}&lon=${lon}`);
        if (data && data.risk_score !== undefined) {
            const riskInfo = getRiskInfo(data.risk_score);

            if (data.risk_score >= 0.7) {
                showEmergencyAlert(data);
            }

            // Show info panel with risk details
            openInfoPanel(data, lat, lon);
        }
    } catch (e) {
        console.warn('Risk check failed:', e);
    }
}

function showEmergencyAlert(data) {
    const banner = document.createElement('div');
    banner.id = 'emergency-banner';
    banner.style.cssText = `
        position: fixed; top: 0; left: 0; right: 0; bottom: 0;
        background: rgba(220, 38, 38, 0.95); color: white;
        display: flex; align-items: center; justify-content: center;
        z-index: 2000; flex-direction: column; text-align: center;
        padding: 20px;
    `;

    banner.innerHTML = `
        <div style="font-size:48px;margin-bottom:20px">⚠️</div>
        <h2 style="font-size:24px;margin-bottom:10px">You are in a HIGH FLOOD RISK Area</h2>
        <p style="font-size:16px;margin-bottom:20px">Risk level: ${data.risk_score.toFixed(2)}</p>
        <div style="display:flex;gap:10px;flex-wrap:wrap;justify-content:center">
            <button onclick="findSafestRoute()" class="btn btn-primary">Find Safe Route</button>
            <button onclick="showSafeZones()" class="btn btn-secondary">Find Safe Zone</button>
            <button onclick="showEmergencyContacts()" class="btn btn-secondary">Emergency Contacts</button>
            <button onclick="closeEmergencyBanner()" class="btn btn-danger">Dismiss</button>
        </div>
    `;

    document.body.appendChild(banner);
}

function openInfoPanel(data, lat, lon) {
    const section = document.getElementById('gis-info-section');
    if (!section) return;

    const riskInfo = getRiskInfo(data.risk_score || 0);

    document.getElementById('info-name').textContent = data.zone_name || 'Current Location';
    document.getElementById('info-risk').textContent = `${(data.risk_score * 100).toFixed(0)}%`;
    document.getElementById('info-severity').textContent = data.severity || riskInfo.label;
    document.getElementById('info-updated').textContent = data.data_confidence || 'live';

    const panel = document.getElementById('gis-panel');
    if (panel) panel.classList.add('open');
}

function openRouteMode() {
    const panel = document.getElementById('gis-panel');
    const routeSection = document.getElementById('gis-route-section');
    if (panel) panel.classList.add('open');
    if (routeSection) {
        routeSection.scrollIntoView({ behavior: 'smooth' });
    }
}

function closeRoutePanel() {
    const panel = document.getElementById('gis-panel');
    if (panel) panel.classList.remove('open');
}

function closeEmergencyBanner() {
    const banner = document.getElementById('emergency-banner');
    if (banner) banner.remove();
}

async function showNearbyEmergencyServices(lat, lon) {
    try {
        const data = await cachedFetch(`/api/v1/emergency-services/?lat=${lat}&lon=${lon}`);
        if (data && (data.hospitals?.length || data.shelters?.length)) {
            addEmergencyMarkers(data);
        }
    } catch (e) {
        console.warn('Failed to load emergency services:', e);
    }
}

function addEmergencyMarkers(services) {
    // Add hospital markers (red cross)
    services.hospitals?.forEach(h => {
        const marker = L.marker([h.lat, h.lon], {
            icon: L.divIcon({
                className: 'emergency-marker hospital',
                html: '🏥',
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            }),
        }).bindPopup(`<strong>Hospital</strong><br>${h.name}`);
        marker.addTo(gisMap);
    });

    // Add shelter markers
    services.shelters?.forEach(s => {
        const marker = L.marker([s.lat, s.lon], {
            icon: L.divIcon({
                className: 'emergency-marker shelter',
                html: '🛖',
                iconSize: [24, 24],
                iconAnchor: [12, 12],
            }),
        }).bindPopup(`<strong>Safe Shelter</strong><br>${s.name}`);
        marker.addTo(gisMap);
    });
}

async function findSafestRoute() {
    const userPos = userMarker ? userMarker.getLatLng() : null;
    if (!userPos) {
        showError('Current location not available.');
        return;
    }

    // Open route panel and set origin
    openRouteMode();
    routeState.origin = { lat: userPos.lat, lng: userPos.lng };
    const originInput = document.getElementById('origin-input');
    if (originInput) originInput.value = `${userPos.lat.toFixed(6)}, ${userPos.lng.toFixed(6)}`;
}

function findSafeRouteFromCell(h3Index) {
    openRouteMode();
}

function showSafeZones() {
    // Filter and show only safe zones on map
    if (h3Layer) {
        h3Layer.eachLayer(layer => {
            const props = layer.options?.cellData || {};
            if (props.risk_score > 0.4) {
                gisMap.removeLayer(layer);
            }
        });
    }
}

function showEmergencyContacts() {
    const contacts = `
        Emergency Contacts:
        - Kenya Red Cross: 1199
        - Emergency Services: 999 / 112
        - Flood Rescue: Contact nearest police station
    `;
    alert(contacts);
}

function showError(message) {
    const el = document.createElement('div');
    el.textContent = message;
    el.style.cssText = `
        position: fixed; bottom: 80px; left: 50%; transform: translateX(-50%);
        background: #dc2626; color: white; padding: 12px 20px; border-radius: 8px;
        z-index: 1100; font-size: 14px;
    `;
    document.body.appendChild(el);
    setTimeout(() => el.remove(), 4000);
}

function debounce(fn, delay = 300) {
    let timer;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn.apply(this, args), delay);
    };
}

const debounceLoadH3Cells = debounce(() => loadH3Cells(), 500);

// Expose for template
window.initGisDashboard = initGisDashboard;
window.getRiskInfo = getRiskInfo;
window.loadH3Cells = loadH3Cells;