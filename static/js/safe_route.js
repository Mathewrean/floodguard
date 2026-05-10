const routeState = {
    map: null,
    origin: null,
    destination: null,
    profile: 'balanced',
    clickMode: 'origin',
    markers: {},
    routeLayers: [],
};

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
        status.textContent = snap ? `${snap.status.replaceAll('_', ' ')} • confidence ${confidence}` : 'Point selected';
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

    routeState.clickMode = type === 'origin' ? 'destination' : 'destination';
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
        fastest: '#2B83D3',
    };
    const weights = { safest: 7, balanced: 6, fastest: 4 };
    const bounds = [];

    routes.forEach(route => {
        const colour = colours[route.profile] || '#2B83D3';
        const layer = L.polyline(route.geometry, {
            color: colour,
            weight: weights[route.profile] || 5,
            opacity: 0.88,
            lineCap: 'round',
            lineJoin: 'round',
        }).bindPopup(`
            <strong>${escapeHTML(route.label)}</strong><br>
            Safety: ${route.safety_score}/100<br>
            Distance: ${(route.distance_m / 1000).toFixed(2)} km<br>
            ETA: ${route.duration_min} min
        `).addTo(routeState.map);
        routeState.routeLayers.push(layer);
        route.geometry.forEach(point => bounds.push(point));
    });

    if (bounds.length) {
        routeState.map.fitBounds(bounds, { padding: [40, 40] });
    }
}

function renderRouteCards(routes, engine) {
    const container = document.getElementById('route-results');
    if (!container) return;
    if (!routes.length) {
        container.innerHTML = '<div class="route-result-card">No route candidates available.</div>';
        return;
    }

    container.innerHTML = routes.map(route => `
        <article class="route-result-card ${route.profile}">
            <div>
                <strong>${escapeHTML(route.label)}</strong>
                <span>${route.crossed_zones.length ? `Risk zones: ${route.crossed_zones.map(escapeHTML).join(', ')}` : 'No mapped risk zones crossed'}</span>
            </div>
            <div class="route-result-metrics">
                <span>${route.safety_score}/100 safety</span>
                <span>${(route.distance_m / 1000).toFixed(2)} km</span>
                <span>${route.duration_min} min</span>
            </div>
        </article>
    `).join('') + `<p class="route-engine-note">${escapeHTML(engine.algorithm)}</p>`;
}

async function calculateSafeRoute() {
    if (!routeState.origin || !routeState.destination) {
        setRouteStatus('Set both origin and destination first.', 'warning');
        return;
    }

    setRouteStatus('Calculating safety-weighted route options...');
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
        setRouteStatus('Route options ready.', 'success');
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

function initSafeRoutePage() {
    const mapElement = document.getElementById('safe-route-map');
    if (!mapElement || typeof L === 'undefined') return;

    routeState.map = createBaseMap('safe-route-map', 14);
    renderZones(routeState.map, { fitBounds: false });

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
        gpsButton.addEventListener('click', async () => {
            gpsButton.disabled = true;
            gpsButton.textContent = 'Locating...';
            const location = await locateUser(routeState.map);
            const coord = Array.isArray(location)
                ? { lat: Number(location[0]), lng: Number(location[1]) }
                : { lat: location.lat, lng: location.lng };
            await snapRoutePoint('origin', coord);
            gpsButton.disabled = false;
            gpsButton.textContent = 'Use GPS';
        });
    }

    const calculateButton = document.getElementById('calculate-route');
    if (calculateButton) calculateButton.addEventListener('click', calculateSafeRoute);
    initModeSelector();
    setRouteStatus('Use GPS or click the map to choose an origin.');
}

document.addEventListener('DOMContentLoaded', initSafeRoutePage);
