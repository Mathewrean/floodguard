const routeState = {
    map: null,
    origin: null,
    destination: null,
    profile: 'balanced',
    clickMode: 'origin',
    markers: {},
    routeLayers: [],
};

const SAFE_ROUTE_DEFAULT_LOCATION = { lat: -1.2921, lng: 36.8219 };

function formatCoord(coord) {
    return `${coord.lat.toFixed(6)}, ${coord.lng.toFixed(6)}`;
}

function setRouteStatus(message, tone = 'info') {
    const status = document.getElementById('route-status');
    if (!status) return;
    status.textContent = message;
    status.dataset.tone = tone;
}

function setRoutePoint(type, coord, snap = null) {
    routeState[type] = coord;
    const input = document.getElementById(`${type}-input`);
    const status = document.getElementById(`${type}-snap-status`);
    if (input) input.value = formatCoord(coord);
    if (status) {
        const confidence = snap && snap.confidence ? `${Math.round(snap.confidence * 100)}%` : 'pending';
        const snapStatus = snap && typeof snap.status === 'string'
            ? snap.status.replaceAll('_', ' ')
            : 'Point selected';
        status.textContent = snap && snap.status ? `${snapStatus} • confidence ${confidence}` : 'Point selected';
    }

    const iconHtml = type === 'origin' ? '●' : '◆';
    const markerClass = type === 'origin' ? 'route-marker origin' : 'route-marker destination';
    const latLng = [coord.lat, coord.lng];
    if (routeState.markers[type]) {
        routeState.markers[type].setLatLng(latLng);
    } else {
        routeState.markers[type] = L.marker(latLng, {
            icon: L.divIcon({ className: markerClass, html: iconHtml, iconSize: [22, 22] })
        }).addTo(routeState.map);
    }

    routeState.clickMode = type === 'origin' ? 'destination' : 'origin';
}

async function snapRoutePoint(type, coord) {
    setRouteStatus(`Snapping ${type} to navigable route data...`);
    try {
        const snap = await fetchJSON('/api/v1/safe-route/snap/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({ coordinate: coord })
        });
        if (!snap || !snap.coordinate || typeof snap.coordinate.lat !== 'number' || typeof snap.coordinate.lng !== 'number') {
            throw new Error('Invalid snap response');
        }
        setRoutePoint(type, snap.coordinate, snap);
        if (navigator.vibrate) navigator.vibrate(18);
        setRouteStatus(type === 'origin' ? 'Origin set. Click destination.' : 'Destination set. Calculate a route.');
    } catch (error) {
        setRoutePoint(type, coord, null);
        setRouteStatus(`Could not snap ${type}; using selected coordinate.`, 'warning');
    }
}

function clearRoutes() {
    routeState.routeLayers.forEach(layer => routeState.map.removeLayer(layer));
    routeState.routeLayers = [];
}

function renderRoutes(routes) {
    clearRoutes();
    const colours = {
        safest: '#16A34A',
        balanced: '#D97706',
        fastest: '#DC2626',
    };
    const weights = { safest: 7, balanced: 6, fastest: 5 };
    const bounds = [];

    routes.forEach(route => {
        const colour = colours[route.profile] || '#2B83D3';
        const geometry = Array.isArray(route.geometry) ? route.geometry : [];
        const layer = L.polyline(geometry, {
            color: colour,
            weight: weights[route.profile] || 5,
            opacity: 0.88,
            lineCap: 'round',
            lineJoin: 'round',
        }).bindPopup(`
            <strong>${escapeHTML(route.label)}</strong><br>
            Distance: ${(route.distance_km || route.distance_m / 1000).toFixed(2)} km<br>
            ETA: ${(route.duration_minutes || route.duration_min).toFixed(1)} min<br>
            Flood Risk: ${route.risk_label || 'N/A'} (${(route.flood_risk || 0) * 100}%)
        `).addTo(routeState.map);
        routeState.routeLayers.push(layer);
        geometry.forEach(point => {
            if (Array.isArray(point) && point.length >= 2) {
                bounds.push([point[1], point[0]]);
            }
        });
    });

    if (bounds.length) {
        try {
            routeState.map.fitBounds(bounds, { padding: [40, 40] });
        } catch (e) {}
    }
}

function renderRouteCards(routes, engine) {
    const container = document.getElementById('route-results');
    if (!container) return;
    if (!routes.length) {
        container.innerHTML = '<div class="route-result-card">No route candidates available.</div>';
        return;
    }

    container.innerHTML = routes.map(route => {
        const risk = route.flood_risk || 0;
        const riskLabel = route.risk_label || 'N/A';
        const riskPct = (risk * 100).toFixed(0);
        const distance = route.distance_km || (route.distance_m / 1000);
        const duration = route.duration_minutes || route.duration_min;
        
        return `
            <article class="route-result-card ${route.profile}">
                <div>
                    <strong>${escapeHTML(route.label)}</strong>
                    <span class="route-risk-badge ${riskLabel.toLowerCase()}">${riskLabel} (${riskPct}%)</span>
                </div>
                <div class="route-result-metrics">
                    <span>${distance.toFixed(2)} km</span>
                    <span>${duration.toFixed(1)} min</span>
                </div>
            </article>
        `;
    }).join('') + `<p class="route-engine-note">${escapeHTML(engine.algorithm || 'FloodGuard Safe Route')}</p>`;
}

async function calculateSafeRoute() {
    if (!routeState.origin || !routeState.destination) {
        setRouteStatus('Set both origin and destination first.', 'warning');
        return;
    }

    setRouteStatus('Calculating safe routes...');
    
    // Try GraphHopper + H3 endpoint first (GET)
    try {
        const params = new URLSearchParams({
            origin_lat: routeState.origin.lat,
            origin_lon: routeState.origin.lng,
            dest_lat: routeState.destination.lat,
            dest_lon: routeState.destination.lng,
            vehicle: 'car',
        });
        
        const data = await fetchJSON(`/api/v1/safe-route/?${params.toString()}`);
        if (data.routes && data.routes.length) {
            renderRoutes(data.routes);
            renderRouteCards(data.routes, data.engine || {});
            setRouteStatus(data.recommendation || 'Route options ready.', 'success');
            return;
        }
    } catch (error) {
        console.warn('GraphHopper route failed, falling back to prototype:', error);
    }
    
    // Fallback to prototype POST endpoint
    try {
        const data = await fetchJSON('/api/v1/safe-route/', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
                'X-CSRFToken': getCookie('csrftoken')
            },
            body: JSON.stringify({
                origin: routeState.origin,
                destination: routeState.destination,
                profile: routeState.profile,
            })
        });
        renderRoutes(data.routes || []);
        renderRouteCards(data.routes || [], data.engine || {});
        setRouteStatus('Route options ready (prototype mode).', 'success');
    } catch (error) {
        setRouteStatus('Safe-route service failed. Check coordinates and try again.', 'error');
    }
}

function initModeSelector() {
    document.querySelectorAll('.mode-chip').forEach(button => {
        button.addEventListener('click', () => {
            document.querySelectorAll('.mode-chip').forEach(item => item.classList.remove('active'));
            button.classList.add('active');
            routeState.profile = button.dataset.profile || 'balanced';
        });
    });
}

async function initSafeRoutePage() {
    const mapElement = document.getElementById('safe-route-map');
    if (!mapElement || typeof L === 'undefined') return;

    routeState.map = createBaseMap('safe-route-map', 14);
    const zones = await fetchJSON('/api/v1/zones/').then(normaliseList).catch(() => []);
    renderZones(routeState.map, zones, { fitBounds: false });
    setRoutePoint('origin', SAFE_ROUTE_DEFAULT_LOCATION, { status: 'default_nairobi', confidence: 1 });
    routeState.clickMode = 'destination';

    routeState.map.on('click', event => {
        const coord = { lat: event.latlng.lat, lng: event.latlng.lng };
        snapRoutePoint(routeState.clickMode, coord);
    });

    routeState.map.on('zoomend', () => {
        const shell = document.querySelector('.safe-route-map-shell');
        if (shell) shell.classList.toggle('precision-mode', routeState.map.getZoom() >= 17);
    });

    const gpsButton = document.getElementById('use-current-location');
    if (gpsButton) {
        const defaultLabel = gpsButton.textContent;
        gpsButton.addEventListener('click', async () => {
            gpsButton.disabled = true;
            gpsButton.textContent = 'Locating...';
            try {
                const location = await locateUser(routeState.map);
                if (!location) {
                    setRouteStatus('Location unavailable. Click the map to set your origin.', 'warning');
                    return;
                }

                const coord = Array.isArray(location)
                    ? { lat: Number(location[0]), lng: Number(location[1]) }
                    : { lat: location.lat, lng: location.lng };
                await snapRoutePoint('origin', coord);
            } finally {
                gpsButton.disabled = false;
                gpsButton.textContent = defaultLabel;
            }
        });
    }

    const calculateButton = document.getElementById('calculate-route');
    if (calculateButton) calculateButton.addEventListener('click', calculateSafeRoute);
    initModeSelector();
    setRouteStatus('Default origin is Nairobi. Use GPS to replace it or click the map.');
}

document.addEventListener('DOMContentLoaded', initSafeRoutePage);
