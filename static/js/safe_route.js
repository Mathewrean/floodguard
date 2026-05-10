/**
 * Safe Route Navigation JavaScript
 * Handles two-click workflow for origin/destination selection and route calculation
 */

let safeRouteMap = null;
let originMarker = null;
let destinationMarker = null;
let directRouteLayer = null;
let safeRouteLayer = null;
let routeModeActive = false;

/**
 * Initialize safe route functionality on a Leaflet map
 * @param {L.Map} map - The Leaflet map instance
 */
function initSafeRoute(map) {
    safeRouteMap = map;
    
    // Add route control panel to map
    const routePanel = L.control({position: 'topright'});
    routePanel.onAdd = function() {
        const div = L.DomUtil.create('div', 'route-panel');
        div.innerHTML = `
            <div class="route-panel-title">Safe Route</div>
            <div class="route-steps">
                <div class="route-step step1 active" id="route-step-1">1️⃣ Click Origin</div>
                <div class="route-step step2" id="route-step-2">2️⃣ Click Destination</div>
                <div class="route-step step3" id="route-step-3">3️⃣ Get Route</div>
            </div>
            <button id="get-route-btn" class="btn-route-disabled" disabled>Get Safe Route</button>
            <button id="clear-route-btn" class="btn-clear" style="display:none;">Clear Route</button>
            <div id="route-info-panel" class="route-result" style="display:none;"></div>
            <div id="mode-toggle">
                <button id="explore-mode-btn" class="mode-btn active">🗺 Explore Mode</button>
                <button id="route-mode-btn" class="mode-btn">🧭 Route Mode</button>
            </div>
        `;
        return div;
    };
    routePanel.addTo(safeRouteMap);
    
    // Get DOM elements
    const getRouteBtn = document.getElementById('get-route-btn');
    const clearRouteBtn = document.getElementById('clear-route-btn');
    const routeInfoPanel = document.getElementById('route-info-panel');
    const exploreModeBtn = document.getElementById('explore-mode-btn');
    const routeModeBtn = document.getElementById('route-mode-btn');
    const routeSteps = {
        step1: document.getElementById('route-step-1'),
        step2: document.getElementById('route-step-2'),
        step3: document.getElementById('route-step-3')
    };
    
    // Map click handler for route mode
    function onMapClick(e) {
        if (!routeModeActive) return;
        
        const { lat, lng } = e.latlng;
        
        if (!originMarker) {
            // First click: set origin
            setOriginMarker(lat, lng);
            updateRouteSteps(2);
        } else if (!destinationMarker) {
            // Second click: set destination
            setDestinationMarker(lat, lng);
            updateRouteSteps(3);
            // Enable get route button
            getRouteBtn.disabled = false;
            getRouteBtn.classList.remove('btn-route-disabled');
            getRouteBtn.classList.add('btn-route-enabled');
        } else {
            // Third click: reset
            resetRouteSelection();
        }
    }
    
    safeRouteMap.on('click', onMapClick);
    
    // Get route button handler
    getRouteBtn.addEventListener('click', async () => {
        if (!originMarker || !destinationMarker) return;
        
        getRouteBtn.disabled = true;
        getRouteBtn.innerHTML = 'Calculating...';
        
        try {
            const origin = originMarker.getLatLng();
            const destination = destinationMarker.getLatLng();
            
            const response = await fetch(`/api/v1/safe-route/?from_lat=${origin.lat}&from_lon=${origin.lng}&to_lat=${destination.lat}&to_lon=${destination.lng}`);
            
            if (!response.ok) {
                throw new Error(`HTTP error! status: ${response.status}`);
            }
            
            const data = await response.json();
            displayRouteResult(data);
        } catch (error) {
            console.error('Route calculation failed:', error);
            routeInfoPanel.innerHTML = '<p class="error">Route calculation failed. Please try again.</p>';
            routeInfoPanel.style.display = 'block';
        } finally {
            getRouteBtn.disabled = false;
            getRouteBtn.innerHTML = 'Get Safe Route';
        }
    });
    
    // Clear route button handler
    clearRouteBtn.addEventListener('click', resetRouteSelection);
    
    // Mode toggle handlers
    exploreModeBtn.addEventListener('click', () => {
        routeModeActive = false;
        exploreModeBtn.classList.add('active');
        routeModeBtn.classList.remove('active');
        // Optionally disable map click for route setting
    });
    
    routeModeBtn.addEventListener('click', () => {
        routeModeActive = true;
        exploreModeBtn.classList.remove('active');
        routeModeBtn.classList.add('active');
        // Reset if in middle of route selection
        if (originMarker && !destinationMarker) {
            // Keep origin, reset destination step
            updateRouteSteps(2);
        } else if (!originMarker) {
            resetRouteSelection();
        }
    });
}

/**
 * Set origin marker on the map
 * @param {number} lat - Latitude
 * @param {number} lng - Longitude
 */
function setOriginMarker(lat, lng) {
    if (originMarker) {
        originMarker.setLatLng([lat, lng]);
    } else {
        originMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'origin-marker',
                html: '🟢',
                iconSize: [30, 30]
            })
        }).bindPopup('Origin').addTo(safeRouteMap);
    }
    safeRouteMap.setView([lat, lng], Math.max(safeRouteMap.getZoom(), 13));
}

/**
 * Set destination marker on the map
 * @param {number} lat - Latitude
 * @param {number} lng - Longitude
 */
function setDestinationMarker(lat, lng) {
    if (destinationMarker) {
        destinationMarker.setLatLng([lat, lng]);
    } else {
        destinationMarker = L.marker([lat, lng], {
            icon: L.divIcon({
                className: 'destination-marker',
                html: '🔴',
                iconSize: [30, 30]
            })
        }).bindPopup('Destination').addTo(safeRouteMap);
    }
}

/**
 * Reset route selection and clear all markers/layers
 */
function resetRouteSelection() {
    // Remove markers
    if (originMarker) {
        safeRouteMap.removeLayer(originMarker);
        originMarker = null;
    }
    if (destinationMarker) {
        safeRouteMap.removeLayer(destinationMarker);
        destinationMarker = null;
    }
    
    // Remove route layers
    if (directRouteLayer) {
        safeRouteMap.removeLayer(directRouteLayer);
        directRouteLayer = null;
    }
    if (safeRouteLayer) {
        safeRouteMap.removeLayer(safeRouteLayer);
        safeRouteLayer = null;
    }
    
    // Reset UI
    document.getElementById('get-route-btn').disabled = true;
    document.getElementById('get-route-btn').className = 'btn-route-disabled';
    document.getElementById('clear-route-btn').style.display = 'none';
    document.getElementById('route-info-panel').style.display = 'none';
    updateRouteSteps(1);
    
    // Re-center to user location if available
    if (window._lastKnownPosition) {
        safeRouteMap.setView([window._lastKnownPosition.lat, window._lastKnownPosition.lng], safeRouteMap.getZoom());
    }
}

/**
 * Update the route step indicators
 * @param {number} step - The step to activate (1, 2, or 3)
 */
function updateRouteSteps(step) {
    document.getElementById('route-step-1').className = `route-step step1 ${step === 1 ? 'active' : ''}`;
    document.getElementById('route-step-2').className = `route-step step2 ${step === 2 ? 'active' : ''}`;
    document.getElementById('route-step-3').className = `route-step step3 ${step === 3 ? 'active' : ''}`;
}

/**
 * Display the route calculation result on the map and in the info panel
 * @param {Object} data - The route data from the API
 */
function displayRouteResult(data) {
    // Clear previous routes
    if (directRouteLayer) {
        safeRouteMap.removeLayer(directRouteLayer);
    }
    if (safeRouteLayer) {
        safeRouteMap.removeLayer(safeRouteLayer);
    }
    
    // Add direct route (dashed red)
    if (data.direct_route && data.direct_route.coordinates) {
        const directLatLngs = data.direct_route.coordinates.map(coord => [coord[1], coord[0]]); // Convert [lon,lat] to [lat,lng]
        directRouteLayer = L.polyline(directLatLngs, {
            color: '#C0392B',
            weight: 3,
            opacity: 0.6,
            dashArray: '5, 5'
        }).addTo(safeRouteMap);
    }
    
    // Add safe route (solid green)
    if (data.safe_route && data.safe_route.coordinates) {
        const safeLatLngs = data.safe_route.coordinates.map(coord => [coord[1], coord[0]]); // Convert [lon,lat] to [lat,lng]
        safeRouteLayer = L.polyline(safeLatLngs, {
            color: '#27AE60',
            weight: 4,
            opacity: 0.9
        }).addTo(safeRouteMap);
        
        // Fit bounds to show both routes if they exist
        if (directRouteLayer && safeRouteLayer) {
            const group = L.featureGroup([directRouteLayer, safeRouteLayer]);
            safeRouteMap.fitBounds(group.getBounds(), { padding: [50, 50] });
        } else if (safeRouteLayer) {
            safeRouteMap.setView(safeRouteLayer.getBounds().getCenter(), Math.max(safeRouteMap.getZoom(), 13));
        }
    }
    
    // Update info panel
    const routeInfoPanel = document.getElementById('route-info-panel');
    let infoHTML = '';
    
    if (data.safe_route_extra_distance_km !== undefined) {
        infoHTML += `<p><strong>Safe Route Found</strong> — adds ${data.safe_route_extra_distance_km.toFixed(1)} km but avoids ${data.risk_zones_on_direct?.length || 0} flood zones</p>`;
    }
    
    if (data.risk_zones_on_safe && data.risk_zones_on_safe.length > 0) {
        infoHTML += `<p class="warning">⚠️ The safe route passes through: ${data.risk_zones_on_safe.join(', ')}</p>`;
    } else {
        infoHTML += `<p class="success">✅ All clear — no high-risk zones on the safe route</p>`;
    }
    
    if (data.recommendation) {
        infoHTML += `<p><em>${data.recommendation}</em></p>`;
    }
    
    routeInfoPanel.innerHTML = infoHTML;
    routeInfoPanel.style.display = 'block';
    document.getElementById('clear-route-btn').style.display = 'inline-block';
    
    // Show success feedback
    showTemporaryMessage('Route calculated successfully!', 'success');
}

/**
 * Show a temporary message to the user
 * @param {string} message - The message to display
 * @param {string} type - The type of message (success, warning, error)
 */
function showTemporaryMessage(message, type = 'info') {
    // Remove any existing message
    const existing = document.querySelector('.temporary-message');
    if (existing) existing.remove();
    
    const div = L.DomUtil.create('div', `temporary-message ${type}`);
    div.textContent = message;
    div.style.position = 'fixed';
    div.style.bottom = '20px';
    div.style.left = '50%';
    div.style.transform = 'translateX(-50%)';
    div.style.backgroundColor = type === 'success' ? 'rgba(39, 174, 96, 0.9)' :
                               type === 'warning' ? 'rgba(230, 126, 34, 0.9)' :
                               type === 'error' ? 'rgba(192, 57, 43, 0.9)' :
                               'rgba(0, 0, 0, 0.8)';
    div.style.color = 'white';
    div.style.padding = '10px 20px';
    div.style.borderRadius = '6px';
    div.style.zIndex = '1000';
    div.style.fontSize = '14px';
    div.style.boxShadow = '0 2px 10px rgba(0,0,0,0.2)';
    
    document.body.appendChild(div);
    
    // Remove after 3 seconds
    setTimeout(() => {
        if (div.parentNode) {
            div.parentNode.removeChild(div);
        }
    }, 3000);
}

// Export functions for use in other scripts
window.initSafeRoute = initSafeRoute;
window.resetRouteSelection = resetRouteSelection;