// FloodGuard GIS Dashboard - H3-based Dynamic Risk Zoning
// Implements modern GIS flood intelligence with location search and safe route integration

const RISK_COLORS = {
    SAFE: { color: '#059669', opacity: 0.25 },
    LOW: { color: '#16A34A', opacity: 0.25 },
    MODERATE: { color: '#D97706', opacity: 0.35 },
    HIGH: { color: '#EA580C', opacity: 0.45 },
    CRITICAL: { color: '#DC2626', opacity: 0.50 },
    EXTREME: { color: '#7F1D1D', opacity: 0.60 },
};

const RISKS = [
    { threshold: 0.85, label: 'CRITICAL', level: 'CRITICAL', color: '#DC2626' },
    { threshold: 0.70, label: 'HIGH', level: 'HIGH', color: '#EA580C' },
    { threshold: 0.40, label: 'MODERATE', level: 'MODERATE', color: '#D97706' },
    { threshold: 0.20, label: 'LOW', level: 'LOW', color: '#16A34A' },
    { threshold: 0.0, label: 'SAFE', level: 'SAFE', color: '#059669' },
];

const FORECAST_RISK_COLORS = {
    SAFE: { color: '#059669', opacity: 0.40, dash: true },
    LOW: { color: '#16A34A', opacity: 0.40, dash: true },
    MODERATE: { color: '#D97706', opacity: 0.40, dash: true },
    HIGH: { color: '#EA580C', opacity: 0.40, dash: true },
    CRITICAL: { color: '#DC2626', opacity: 0.40, dash: true },
    EXTREME: { color: '#7F1D1D', opacity: 0.40, dash: true },
};

function getRiskInfo(score) {
    const num = Number(score) || 0;
    for (const risk of RISKS) {
        if (num >= risk.threshold) return risk;
    }
    return RISKS[RISKS.length - 1];
}

function getRiskBand(score) {
    const num = Number(score) || 0;
    if (num >= 0.85) return { colour: '#DC2626', label: 'CRITICAL' };
    if (num >= 0.70) return { colour: '#EA580C', label: 'HIGH' };
    if (num >= 0.40) return { colour: '#D97706', label: 'MODERATE' };
    if (num >= 0.20) return { colour: '#16A34A', label: 'LOW' };
    return { colour: '#059669', label: 'SAFE' };
}

let gisMap = null;
let h3Layer = null;
let h3GridLayer = null;
let userMarker = null;
let selectedCell = null;
let routeState = { origin: null, destination: null, profile: 'balanced' };
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

    // Add English-labeled base layer (Esri World Street Map shows English labels globally)
    const streetLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Street_Map/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 19,
    }).addTo(gisMap);

    // Add satellite layer
    const satelliteLayer = L.tileLayer('https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}', {
        attribution: 'Tiles &copy; Esri',
        maxZoom: 19,
    });

    // Layer control
    const baseLayers = { 'Street Map': streetLayer, 'Satellite': satelliteLayer };
    L.control.layers(baseLayers, {}, { position: 'topright' }).addTo(gisMap);

    // Add scale control
    L.control.scale({ position: 'bottomright', metric: true, imperial: false }).addTo(gisMap);

    // Add compass control
    addCompassControl();

    // Bind UI events
    bindGisControls();

    // Render risk legend
    renderRiskLegend();

    // Load zones, readings, and the actual H3 risk cells for the initial viewport.
    await Promise.all([loadZones(), loadReadings()]);
    await loadH3Cells();

    // Re-fetch on zoom with animated transition
    let zoomDebounce;
    gisMap.on('zoomend', () => {
        clearTimeout(zoomDebounce);
        zoomDebounce = setTimeout(() => {
            loadH3CellsWithAnimation();
        }, 300);
    });
    gisMap.on('moveend', debounce(loadH3Cells, 350));
    
    // Connect WebSocket for live updates
    connectFloodMapSocket();
}

function renderRiskLegend() {
    const legendEl = document.querySelector('.gis-risk-legend');
    if (!legendEl) return;
    
    const levels = ['CRITICAL', 'HIGH', 'MODERATE', 'LOW', 'SAFE', 'EXTREME'];
    const ranges = {
        CRITICAL: '≥ 0.85',
        HIGH: '≥ 0.70',
        MODERATE: '≥ 0.40',
        LOW: '≥ 0.20',
        SAFE: '< 0.20',
        EXTREME: '≥ 0.95',
    };
    
    legendEl.innerHTML = levels.map(level => {
        const band = RISK_COLORS[level] || { color: '#888888', opacity: 0.25 };
        return `
            <div class="legend-item" style="display:flex;align-items:center;gap:6px;margin-bottom:4px">
                <span style="display:inline-block;width:16px;height:16px;border-radius:3px;background:${band.color};opacity:${band.opacity};border:1px solid ${band.color}"></span>
                <span style="font-size:12px;font-weight:600">${level}</span>
                <span style="font-size:11px;color:#666">${ranges[level]}</span>
            </div>
        `;
    }).join('');
}

async function loadH3Cells() {
    if (!gisMap) return;
    const bounds = gisMap.getBounds();
    if (!bounds.isValid()) return;

    const zoom = gisMap.getZoom();
    const isForecast = document.getElementById('gis-forecast-toggle')?.checked || false;
    const forecastHours = document.getElementById('gis-forecast-hours')?.value || '24';
    const showInterpolation = document.getElementById('gis-interpolation-toggle')?.checked;
    const showPropagation = window.propagationState && window.propagationState.active;

    const query = new URLSearchParams({
        min_lat: bounds.getSouth().toFixed(6), min_lon: bounds.getWest().toFixed(6),
        max_lat: bounds.getNorth().toFixed(6), max_lon: bounds.getEast().toFixed(6),
        zoom_level: zoom,
    });

    if (isForecast) {
        query.set('forecast', 'true');
        query.set('forecast_hours', forecastHours);
    }

    if (showInterpolation !== undefined) {
        query.set('interpolation', showInterpolation ? 'true' : 'false');
    }

    try {
        const data = await fetchJSON(`/api/v1/h3-cells/?${query}`);

        if (h3GridLayer) h3GridLayer.remove();
        h3GridLayer = L.layerGroup().addTo(gisMap);

        let splitCount = 0;
        let mergeCount = 0;

        (data.cells || []).forEach(cell => {
            const props = cell.properties || {};
            const score = Number(props.risk_score || 0);
            const isForecastCell = props.forecast_horizon_hours !== undefined;
            const isInterpolated = props.interpolated === true;
            const isPropagated = props.propagated === true;
            const propagationHour = props.propagation_hour;

            const band = isForecastCell ? FORECAST_RISK_COLORS[props.risk_level] : RISK_COLORS[props.risk_level];
            let opacity = isForecastCell ? 0.40 : (band?.opacity || 0.25);

            // Interpolated cells at 65% opacity (0.65 * base)
            if (isInterpolated && !isForecastCell) {
                opacity = 0.65;
            }

            // Propagated cells at 55% opacity (lighter tint effect)
            if (isPropagated) {
                opacity = 0.55;
            }

            // Hide interpolated cells if toggle is off
            if (!showInterpolation && isInterpolated) {
                return;
            }

            const color = band?.color || '#888888';

            const layer = L.geoJSON(cell, {
                style: {
                    color: color,
                    fillColor: isPropagated ? _lightenColor(color, 30) : color,
                    weight: isForecastCell ? 2 : (props.split_from ? 3 : 1),
                    opacity: isForecastCell ? 1 : 0.6,
                    fillOpacity: opacity,
                    dashArray: isForecastCell ? '5,5' : (props.merged_from ? '4,3' : undefined),
                }
            });

            let popupContent = `<strong>H3 risk cell</strong><br>`;
            popupContent += `Risk: ${(score * 100).toFixed(0)}%<br>`;
            popupContent += `Risk Level: ${props.risk_level}<br>`;
            popupContent += `Resolution: ${props.resolution} — ${_getResolutionLabel(props.resolution)}<br>`;
            if (isInterpolated) {
                popupContent += `<em>Interpolated estimate</em><br>`;
            }
            if (isForecastCell) {
                popupContent += `Forecast horizon: +${props.forecast_horizon_hours}h<br>`;
                // Hours to impact badge for HIGH/CRITICAL cells
                if (props.risk_level === 'HIGH' || props.risk_level === 'CRITICAL') {
                    const hoursUntil = Math.max(0, Math.floor((props.risk_score > 0.9 ? 0 : 6)));
                    popupContent += `<div style="background:#fff3cd;padding:4px 8px;border-radius:4px;margin-top:4px">⚠ Impact in ~${hoursUntil}h</div>`;
                }
            }
            if (isPropagated) {
                popupContent += `Propagated (hour ${propagationHour})<br>`;
                popupContent += `<button onclick="stopSimulation()" class="btn btn-sm btn-secondary" style="margin-top:4px">Stop Simulation</button>`;
            }
            popupContent += `<small>${escapeHTML(props.h3_index)}</small>`;

            if (props.split_from) {
                popupContent += `<br><small style="color:#666">Split from ${escapeHTML(props.split_from)}</small>`;
            }
            if (props.merged_from) {
                popupContent += `<br><small style="color:#666">Merged from ${props.merged_from.length} cells</small>`;
            }

            // Timeline button for single cell
            if (props.risk_level === 'HIGH' || props.risk_level === 'CRITICAL') {
                popupContent += `<br><button onclick="showTimelinePopup('${props.h3_index}')" class="btn btn-sm btn-primary" style="margin-top:4px">View 48h Timeline</button>`;
                popupContent += `<button onclick="simulatePropagationFromCell('${props.h3_index}')" class="btn btn-sm btn-secondary" style="margin-top:4px">Simulate Propagation</button>`;
            }

            layer.options.cellData = props;
            layer.bindPopup(popupContent);
            layer.addTo(h3GridLayer);

            if (props.split_from) splitCount++;
            if (props.merged_from) mergeCount++;
        });

        // Update info panel with split/merge counts
        const scaleLabel = data.scale_label || '';
        if (scaleLabel) {
            const infoPanel = document.querySelector('.gis-panel-content');
            if (infoPanel) {
                const scaleEl = document.getElementById('gis-scale-label');
                if (!scaleEl) {
                    const div = document.createElement('div');
                    div.id = 'gis-scale-label';
                    div.style.cssText = 'padding:8px 16px;font-size:12px;color:#666;border-bottom:1px solid var(--border);';
                    infoPanel.parentNode.insertBefore(div, infoPanel);
                }
                const el = document.getElementById('gis-scale-label');
                if (el) {
                    el.textContent = `${scaleLabel} | ${splitCount} cells split, ${mergeCount} cells merged`;
                }
            }
        }

        if (!layerVisibility.flood) gisMap.removeLayer(h3GridLayer);
    } catch (e) {
        if (e.message && !e.message.includes('Bounding box is too large')) console.warn('Failed to load H3 cells:', e);
    }
}

function _getResolutionLabel(res) {
    const labels = {
        3: 'Country Scale',
        4: 'Regional Scale',
        5: 'District Scale',
        6: 'Neighbourhood Scale',
        7: 'Street Scale',
        8: 'Building Scale',
    };
    return labels[res] || '';
}

function _lightenColor(hex, percent) {
    if (!hex || hex.length < 7) return hex;
    const num = parseInt(hex.replace('#', ''), 16);
    const amt = Math.round(2.55 * percent);
    const R = (num >> 16) + amt;
    const G = (num >> 8 & 0x00FF) + amt;
    const B = (num & 0x0000FF) + amt;
    return '#' + (0x1000000 + (R < 0 ? 0 : R > 255 ? 255 : R) * 0x10000 +
        (G < 0 ? 0 : G > 255 ? 255 : G) * 0x100 +
        (B < 0 ? 0 : B > 255 ? 255 : B)).toString(16).slice(1);
}

async function loadH3CellsWithAnimation() {
    const zoom = gisMap.getZoom();
    const isForecast = document.getElementById('gis-forecast-toggle')?.checked || false;

    // Store old layer for dissolve animation
    const oldLayer = h3GridLayer;
    if (oldLayer) oldLayer.setOpacity(1);

    // Fade out old layer
    if (oldLayer) {
        oldLayer.setOpacity(0);
        setTimeout(() => {
            if (oldLayer && gisMap.hasLayer(oldLayer)) {
                oldLayer.remove();
            }
        }, 300);
    }

    // Load new cells with animation
    await loadH3Cells();

    // Fade in new layer
    if (h3GridLayer) {
        h3GridLayer.setOpacity(0);
        let opacity = 0;
        const fadeIn = setInterval(() => {
            opacity += 0.1;
            if (opacity >= 1) {
                opacity = 1;
                clearInterval(fadeIn);
            }
            h3GridLayer.setOpacity(opacity);
        }, 30);
    }
}

async function showTimelinePopup(h3Index) {
    try {
        const data = await fetchJSON(`/api/v1/h3-cells/${h3Index}/timeline/`);
        const timeline = data.timeline || [];
        if (!timeline.length) return;

        // Simple bar chart using ASCII/dots
        const maxScore = Math.max(...timeline.map(t => t.predicted_score));
        const chartHeight = 120;
        const barWidth = 6;
        const gap = 2;
        const chartWidth = timeline.length * (barWidth + gap);

        let barsHtml = '';
        timeline.forEach(t => {
            const barHeight = (t.predicted_score / maxScore) * chartHeight;
            const color = t.predicted_level === 'CRITICAL' ? '#DC2626' :
                         t.predicted_level === 'HIGH' ? '#EA580C' :
                         t.predicted_level === 'MODERATE' ? '#D97706' :
                         t.predicted_level === 'LOW' ? '#16A34A' : '#059669';
            barsHtml += `<div style="display:inline-block;width:${barWidth}px;height:${barHeight}px;background:${color};vertical-align:bottom;margin-right:${gap}px" title="Hour ${t.hour}: ${(t.predicted_score * 100).toFixed(0)}% - ${t.predicted_level}"></div>`;
        });

        const container = document.createElement('div');
        container.style.maxWidth = '500px';
        container.innerHTML = `
            <strong>48h Risk Timeline</strong><br>
            <div style="margin-top:8px">
                <div style="height:${chartHeight}px;vertical-align:bottom;background:rgba(0,0,0,0.05);padding:4px;border-radius:4px">
                    ${barsHtml}
                </div>
            </div>
            <div style="margin-top:8px;font-size:11px;color:#666">
                Base risk: ${(data.current_risk_score * 100).toFixed(0)}% (${data.current_risk_level})
            </div>
            <div style="margin-top:4px;font-size:11px">
                Hover bars for hour-level detail
            </div>
        `;

        if (selectedCell && selectedCell.bindPopup) {
            selectedCell.bindPopup(container).openPopup();
        } else {
            L.popup().setContent(container).setLatLng(gisMap.getCenter()).openOn(gisMap);
        }
    } catch (e) {
        console.warn('Timeline fetch failed:', e);
    }
}

let propagationState = { active: false, layer: null, intervalId: null };

async function simulatePropagationFromCell(h3Index) {
    if (propagationState.active) return;

    propagationState.active = true;
    propagationState.layer = L.layerGroup().addTo(gisMap);

    try {
        const data = await fetchJSON(`/api/v1/flood-propagation/?seed_cell=${h3Index}&hours=6`);
        const features = data.features || [];
        const byHour = {};
        features.forEach(f => {
            const hour = f.properties.propagation_hour;
            if (!byHour[hour]) byHour[hour] = [];
            byHour[hour].push(f);
        });

        let currentHour = 0;
        const maxHour = Math.max(...Object.keys(byHour).map(h => parseInt(h)));
        propagationState.intervalId = setInterval(() => {
            const hourFeatures = byHour[currentHour];
            if (hourFeatures) {
                hourFeatures.forEach(f => {
                    const props = f.properties;
                    const band = RISK_COLORS[props.risk_level] || { color: '#888', opacity: 0.5 };
                    L.geoJSON(f, {
                        style: {
                            color: _lightenColor(band.color, 30),
                            fillColor: _lightenColor(band.color, 30),
                            weight: 1,
                            opacity: 0.8,
                            fillOpacity: 0.55,
                        }
                    }).addTo(propagationState.layer);
                });
            }
            currentHour++;
            if (currentHour > maxHour) {
                stopSimulation();
            }
        }, 1000);
    } catch (e) {
        console.warn('Propagation failed:', e);
        propagationState.active = false;
        if (propagationState.layer) propagationState.layer.remove();
    }
}

function stopSimulation() {
    if (propagationState.intervalId) {
        clearInterval(propagationState.intervalId);
        propagationState.intervalId = null;
    }
    if (propagationState.layer) {
        propagationState.layer.remove();
        propagationState.layer = null;
    }
    propagationState.active = false;
}

function createZonePopup(zone) {
    const score = Number(zone.risk_score || 0);
    const band = getRiskBand(score);
    
    return `
        <div style="min-width:200px;font-family:-apple-system,Arial,sans-serif">
            <div style="background:${band.colour};padding:8px 12px;border-radius:6px 6px 0 0">
                <strong style="color:white;font-size:14px">${escapeHTML(zone.name)}</strong>
            </div>
            <div style="padding:10px 12px;background:white">
                <div style="font-size:13px;margin-bottom:6px">
                    <span style="color:${band.colour};font-weight:700">${band.label}</span>
                    <span style="margin-left:8px">${(score * 100).toFixed(0)}% risk</span>
                </div>
                <div style="font-size:12px;color:#666">
                    <div>Threshold: ${(zone.risk_threshold || 0.7) * 100}%</div>
                    <div>Updated: ${timeAgo(zone.updated || zone.created)}</div>
                </div>
                <div style="margin-top:8px">
                    <button onclick="findSafeRouteFromZone(${zone.id})" class="btn btn-sm btn-primary" style="width:100%">Find Safe Route</button>
                </div>
            </div>
        </div>
    `;
}

async function loadZones() {
    if (!gisMap) return;

    try {
        const zones = normaliseList(await fetchJSON('/api/v1/zones/'));
        if (!zones.length) {
            const panel = document.querySelector('.gis-info-section');
            if (panel) {
                panel.innerHTML = '<div style="padding:12px;color:#666">No zones loaded yet. Add flood zones to see risk data.</div>';
            }
            return;
        }

        // Render zone polygons
        if (h3Layer) h3Layer.remove();
        h3Layer = L.layerGroup().addTo(gisMap);

        zones.forEach(zone => {
            const score = Number(zone.risk_score || 0);
            const band = getRiskBand(score);

            // Create GeoJSON from zone polygon
            if (zone.polygon && zone.polygon.coordinates) {
                try {
                    const geojson = {
                        type: 'Feature',
                        geometry: zone.polygon,
                        properties: {
                            id: zone.id,
                            name: zone.name,
                            risk_score: score,
                            severity: band.label,
                            risk_threshold: zone.risk_threshold || 0.7,
                            updated: zone.updated || zone.created
                        }
                    };

                    const polygon = L.geoJSON(geojson, {
                        style: {
                            fillColor: band.colour,
                            fillOpacity: score >= 0.7 ? 0.45 : score >= 0.4 ? 0.35 : 0.25,
                            color: band.colour,
                            weight: 1,
                            opacity: 0.6
                        }
                    }).bindPopup(createZonePopup(zone)).addTo(h3Layer);
                } catch (e) {
                    console.warn('Failed to render zone:', zone.name, e);
                }
            }
        });

        // Fit to zones if we have them
        if (zones.length > 0) {
            const bounds = L.latLngBounds();
            zones.forEach(zone => {
                if (zone.centroid) {
                    bounds.extend([zone.centroid.y, zone.centroid.x]);
                }
            });
            if (bounds.isValid()) {
                gisMap.fitBounds(bounds, { padding: [20, 20] });
            }
        }
    } catch (e) {
        console.warn('Failed to load zones:', e);
    }
}

async function loadReadings() {
    if (!gisMap) return;
    
    try {
        const readings = normaliseList(await fetchJSON('/api/v1/readings/?limit=50'));
        if (!readings.length) return;
        
        const readingsLayer = L.layerGroup();
        readings.forEach(reading => {
            if (!reading.location || !reading.location.coordinates) return;
            const [lon, lat] = reading.location.coordinates;
            const score = Number(reading.risk_score || 0);
            const band = getRiskBand(score);
            
            L.circleMarker([lat, lon], {
                radius: 7,
                color: '#fff',
                weight: 2,
                fillColor: band.colour,
                fillOpacity: 0.9
            }).bindPopup(`
                <strong>Flood Reading</strong><br>
                Water level: ${reading.water_level_metres || 'N/A'}m<br>
                Risk Score: ${(score * 100).toFixed(0)}%<br>
                <small>${timeAgo(reading.timestamp || reading.created_at)}</small>
            `).addTo(readingsLayer);
        });
        readingsLayer.addTo(gisMap);
    } catch (e) {
        console.warn('Failed to load readings:', e);
    }
}

async function connectFloodMapSocket() {
    const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    let reconnectDelay = 2000;
    
    function startSocket() {
        const socket = new WebSocket(`${protocol}//${window.location.host}/ws/flood-map/`);
        
        socket.onopen = () => {
            const status = document.getElementById('ws-status');
            if (status) status.textContent = 'Live';
            reconnectDelay = 2000;
        };
        
        socket.onerror = () => {
            const status = document.getElementById('ws-status');
            if (status) status.textContent = 'Reconnecting...';
        };
        
        socket.onclose = () => {
            if (reconnectDelay < 30000) {
                reconnectDelay *= 2;
            }
            setTimeout(startSocket, reconnectDelay);
        };
        
        socket.onmessage = event => {
            const data = JSON.parse(event.data);
            if (data.type === 'flood.update') {
                loadZones();
                if (data.alert) {
                    const ticker = document.querySelector('.ticker-track');
                    if (ticker && data.alert.message) {
                        const msg = document.createElement('span');
                        msg.textContent = data.alert.message;
                        ticker.appendChild(msg);
                    }
                }
            }
        };
    }
    
    startSocket();
}

function bindGisControls() {
    const searchInput = document.getElementById('gis-search-input');
    const searchBtn = document.getElementById('gis-search-btn');
    const locationBtn = document.getElementById('gis-location-btn');
    const routeBtn = document.getElementById('gis-safe-route-btn');
    const toggleBtn = document.getElementById('gis-panel-toggle');
    const closeBtn = document.getElementById('gis-panel-close');
    const legendToggle = document.getElementById('gis-legend-toggle');

    if (searchBtn) searchBtn.addEventListener('click', doLocationSearch);
    if (searchInput) searchInput.addEventListener('keydown', e => { if (e.key === 'Enter') doLocationSearch(); });
    if (locationBtn) locationBtn.addEventListener('click', useMyLocation);
    if (routeBtn) routeBtn.addEventListener('click', openRouteMode);
    if (toggleBtn) toggleBtn.addEventListener('click', togglePanel);
    if (closeBtn) closeBtn.addEventListener('click', () => {
        const panel = document.getElementById('gis-panel');
        if (panel) panel.classList.add('collapsed');
        const toggle = document.querySelector('#gis-panel-toggle button');
        if (toggle) toggle.setAttribute('aria-expanded', 'false');
    });
    if (legendToggle) legendToggle.addEventListener('click', () => {
        const legend = document.querySelector('.gis-legend');
        if (!legend) return;
        const isCollapsed = legend.classList.toggle('is-collapsed');
        legendToggle.setAttribute('aria-expanded', String(!isCollapsed));
        legendToggle.setAttribute('aria-label', isCollapsed ? 'Expand flood risk legend' : 'Minimize flood risk legend');
        const label = legendToggle.querySelector('.gis-legend-toggle-label');
        if (label) label.textContent = isCollapsed ? 'Show legend' : 'Hide legend';
    });

    gisMap.on('click', (e) => {
        const { lat, lng } = e.latlng;
        if (userMarker) userMarker.remove();
        userMarker = L.marker([lat, lng]).addTo(gisMap);
        checkLocationRisk(lat, lng);
        showNearbyEmergencyServices(lat, lng);
        if (typeof FloodLocation !== 'undefined') {
            FloodLocation.setManual(lat, lng, 5);
        }
    });

    // Layer toggles
    const floodToggle = document.getElementById('layer-flood');
    const satelliteToggle = document.getElementById('layer-satellite');
    if (floodToggle) floodToggle.addEventListener('change', e => {
        layerVisibility.flood = e.target.checked;
        if (h3Layer) {
            layerVisibility.flood ? gisMap.addLayer(h3Layer) : gisMap.removeLayer(h3Layer);
        }
        if (h3GridLayer) {
            layerVisibility.flood ? gisMap.addLayer(h3GridLayer) : gisMap.removeLayer(h3GridLayer);
        }
    });
    const forecastToggle = document.getElementById('gis-forecast-toggle');
    const forecastSlider = document.getElementById('gis-forecast-slider-container');
    if (forecastToggle) {
        forecastToggle.addEventListener('change', () => {
            if (forecastSlider) forecastSlider.style.display = forecastToggle.checked ? 'block' : 'none';
            loadH3Cells();
        });
    }
    const interpolationToggle = document.getElementById('gis-interpolation-toggle');
    if (interpolationToggle) {
        interpolationToggle.addEventListener('change', () => {
            loadH3Cells();
        });
    }
    if (satelliteToggle) satelliteToggle.addEventListener('change', e => {
        layerVisibility.satellite = e.target.checked;
    });
}

function togglePanel() {
    const panel = document.getElementById('gis-panel');
    if (!panel) return;
    const isCollapsed = panel.classList.toggle('collapsed');
    const toggle = document.querySelector('#gis-panel-toggle button');
    if (toggle) toggle.setAttribute('aria-expanded', String(!isCollapsed));
}

async function doLocationSearch() {
    const input = document.getElementById('gis-search-input');
    if (!input) return;

    const query = input.value.trim();
    if (!query) return;

    try {
        let results = [];
        let latlng = null;

        // Check if query is coordinates (lat,lon format)
        const coordMatch = query.match(/^(-?\d+\.?\d*)\s*,\s*(-?\d+\.?\d*)$/);
        if (coordMatch) {
            const lat = parseFloat(coordMatch[1]);
            const lon = parseFloat(coordMatch[2]);
            if (lat >= -90 && lat <= 90 && lon >= -180 && lon <= 180) {
                latlng = [lat, lon];
                results = [{ lat, lon, display_name: `${lat.toFixed(6)}, ${lon.toFixed(6)}` }];
            }
        }

        if (!latlng) {
            const data = await cachedFetch(`/api/v1/geocode/?q=${encodeURIComponent(query)}`);
            results = data.results || [];
        }

        if (results.length) {
            clearSearchMarkers();
            const result = results[0];
            latlng = [result.lat, result.lon];

            const marker = L.marker(latlng).addTo(gisMap);
            marker.bindPopup(`<strong>${result.display_name || query}</strong>`).openPopup();
            searchMarkers.push(marker);

            gisMap.setView(latlng, 13);
            checkLocationRisk(result.lat, result.lon);
            showNearbyEmergencyServices(result.lat, result.lon);

            if (typeof FloodLocation !== 'undefined') {
                FloodLocation.setManual(result.lat, result.lon, 10);
            }
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
    const btn = document.getElementById('gis-location-btn');
    if (btn) {
        btn.disabled = true;
        btn.textContent = 'Locating...';
    }

    FloodLocation.on((loc, isReal) => {
        if (!gisMap || !loc || !Number.isFinite(loc.lat) || !Number.isFinite(loc.lon)) return;
        const latlng = [loc.lat, loc.lon];
        if (userMarker) userMarker.remove();
        userMarker = L.marker(latlng, {
            icon: L.divIcon({
                className: 'pulse-marker',
                html: '',
                iconSize: [20, 20],
                iconAnchor: [10, 10],
            }),
        }).addTo(gisMap);

        if (loc.accuracy && loc.accuracy < 2000) {
            L.circle(latlng, {
                radius: loc.accuracy,
                color: '#EA580C',
                fillOpacity: 0.05,
                weight: 1
            }).addTo(gisMap);
        }

        gisMap.setView(latlng, (loc.accuracy || 500) < 500 ? 15 : 13);
        checkLocationRisk(loc.lat, loc.lon);
        showNearbyEmergencyServices(loc.lat, loc.lon);

        const qualityEl = document.getElementById('gis-location-quality');
        if (qualityEl && typeof FloodLocation !== 'undefined') {
            qualityEl.textContent = `Accuracy: ±${Math.round(loc.accuracy || 0)}m | Quality: ${FloodLocation.qualityLabel} (${FloodLocation.quality}%) | Source: ${loc.source || 'GPS'}`;
        }

        if (btn) {
            btn.disabled = false;
            btn.textContent = 'My Location';
        }
    });

    FloodLocation.detect('auto');
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
    const existing = document.getElementById('emergency-banner');
    if (existing) existing.remove();

    const banner = document.createElement('div');
    banner.id = 'emergency-banner';
    banner.setAttribute('role', 'alert');
    banner.setAttribute('aria-live', 'assertive');
    banner.style.cssText = `
        position: fixed; top: 64px; left: 0; right: 0; z-index: 2000;
        background: linear-gradient(90deg, #083B70, #0B5CAD); color: white;
        padding: 16px 24px; box-shadow: 0 8px 24px rgba(0,0,0,0.3);
        animation: slideDown 0.3s ease-out;
    `;

    banner.innerHTML = `
        <div style="max-width: 1160px; margin: 0 auto; display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap;">
            <div style="display: flex; align-items: center; gap: 12px;">
                <span style="font-size: 24px;" aria-hidden="true">⚠️</span>
                <div>
                    <strong style="font-size: 14px; font-weight: 800; text-transform: uppercase; letter-spacing: 0.5px;">High Flood Risk</strong>
                    <span style="font-size: 13px; opacity: 0.9; margin-left: 8px;">${data.zone_name || 'Current Location'} — ${(data.risk_score * 100).toFixed(0)}% risk</span>
                </div>
            </div>
            <div style="display: flex; gap: 8px; flex-wrap: wrap;">
                <button onclick="findSafestRoute()" class="btn btn-sm" style="background: #fff; color: #083B70;">Find Safe Route</button>
                <button onclick="showSafeZones()" class="btn btn-sm" style="background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.3);">Find Safe Zone</button>
                <button onclick="showEmergencyContacts()" class="btn btn-sm" style="background: rgba(255,255,255,0.2); color: #fff; border: 1px solid rgba(255,255,255,0.3);">Contacts</button>
                <button onclick="closeEmergencyBanner()" class="btn btn-sm" style="background: rgba(255,255,255,0.18); color: #fff;" aria-label="Dismiss emergency alert">✕</button>
            </div>
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
    if (panel) panel.classList.remove('collapsed');
}

function openRouteMode() {
    const panel = document.getElementById('gis-panel');
    const routeSection = document.getElementById('gis-route-section');
    if (panel) panel.classList.remove('collapsed');
    if (routeSection) {
        routeSection.scrollIntoView({ behavior: 'smooth' });
    }
}

function closeRoutePanel() {
    const panel = document.getElementById('gis-panel');
    if (panel) panel.classList.add('collapsed');
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

async function findSafeRouteFromZone(zoneId) {
    try {
        const zone = normaliseList(await fetchJSON('/api/v1/zones/')).find(z => z.id === zoneId);
        if (zone && zone.centroid) {
            openRouteMode();
            const latLng = Array.isArray(zone.centroid) ? { lat: zone.centroid[1], lng: zone.centroid[0] } : { lat: zone.centroid.lat, lng: zone.centroid.lng };
            routeState.destination = latLng;
            const destInput = document.getElementById('destination-input');
            if (destInput) destInput.value = `${latLng.lat.toFixed(6)}, ${latLng.lng.toFixed(6)}`;
        }
    } catch (e) {
        console.warn('Failed to set route from zone:', e);
    }
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
        background: #0B5CAD; color: white; padding: 12px 20px; border-radius: 8px;
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

function addCompassControl() {
    if (!gisMap) return;
    const compass = L.control({ position: 'topright' });
    compass.onAdd = function() {
        const div = L.DomUtil.create('div', 'gis-compass');
        div.innerHTML = '🧭';
        div.title = 'Reset north orientation';
        div.setAttribute('role', 'button');
        div.setAttribute('aria-label', 'Reset map orientation to north');
        div.tabIndex = 0;
        div.addEventListener('click', () => {
            gisMap.setView(gisMap.getCenter(), gisMap.getZoom());
        });
        div.addEventListener('keydown', (e) => {
            if (e.key === 'Enter' || e.key === ' ') {
                e.preventDefault();
                gisMap.setView(gisMap.getCenter(), gisMap.getZoom());
            }
        });
        return div;
    };
    compass.addTo(gisMap);
}

// Expose for template
window.initGisDashboard = initGisDashboard;
window.getRiskInfo = getRiskInfo;
window.loadZones = loadZones;
window.loadH3Cells = loadH3Cells;
