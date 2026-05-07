// Map initialization and zone rendering logic
function initMapPreview() {
    const mapPreview = document.getElementById('map-preview');
    if (!mapPreview) return;

    // Initialize map with default view (centered on a reasonable location)
    const map = L.map('map-preview').setView([0, 0], 2);

    // Add OpenStreetMap tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // Fetch zones from API and add to map
    fetch('/api/v1/zones/')
        .then(response => response.json())
        .then(data => {
            // Handle both paginated (data.results) and plain list (data)
            const zones = data.results || data;
            zones.forEach(zone => {
                // For simplicity, we'll show a marker at the zone's centroid
                // In a real app, you'd want to show the actual polygon
                // Since we don't have the polygon in the API response (it's not included by default in DRF-GIS),
                // we'll use a placeholder or fetch the geometry separately if needed.
                // For now, we'll just show a circle marker for demonstration.
                // Note: The actual implementation would require the polygon data.
                // We'll skip the polygon rendering for the preview and just show a marker at a fixed location for demo.
                // In a production app, you would include the geometry in the API or use a different approach.
                
                // For demo purposes, we'll use a fixed location (Nairobi)
                const marker = L.circleMarker([-1.2921, 36.8219], {
                    radius: 8,
                    fillColor: getRiskColor(zone.risk_threshold || 0.5),
                    color: '#000',
                    weight: 1,
                    opacity: 1,
                    fillOpacity: 0.8
                }).addTo(map);
                
                marker.bindPopup(`
                    <b>${zone.name}</b><br>
                    Risk Threshold: ${(zone.risk_threshold || 0).toFixed(2)}<br>
                    ${zone.manual_override_active ? '<span style="color:red;">Manual Override Active</span>' : ''}
                `);
            });
        })
        .catch(error => {
            console.error('Error loading zones:', error);
            // Show error on map preview
            mapPreview.innerHTML = '<div class="map-error">Unable to load flood zones</div>';
        });
}

function initFullMap() {
    const mapElement = document.getElementById('map');
    if (!mapElement) return;

    // Initialize map
    const map = L.map('map').setView([0, 0], 2);

    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);

    // Add user location marker if available
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => {
                const userLat = position.coords.latitude;
                const userLng = position.coords.longitude;
                
                L.marker([userLat, userLng], {
                    icon: L.divIcon({
                        className: 'user-location-icon',
                        html: '👤',
                        iconSize: [30, 30]
                    })
                }).addTo(map)
                .bindPopup('Your Location')
                .openPopup();
                
                // Optionally, set map view to user location
                map.setView([userLat, userLng], 13);
            },
            error => {
                console.warn('Geolocation not available:', error);
            }
        );
    }

    // Load zones from API
    fetch('/api/v1/zones/')
        .then(response => response.json())
        .then(data => {
            // For full map, we would ideally show polygons
            // Since we don't have polygon data in the default API response, we'll show markers
            // In a real implementation, you would need to include the geometry in the serializer
            data.results.forEach(zone => {
                // Using a fixed point for demo - in reality, you'd use the zone's centroid or a point inside
                const marker = L.circleMarker([-1.2921, 36.8219], {
                    radius: 10,
                    fillColor: getRiskColor(zone.risk_threshold || 0.5),
                    color: '#000',
                    weight: 2,
                    opacity: 1,
                    fillOpacity: 0.7
                }).addTo(map);
                
                marker.bindPopup(`
                    <div class="zone-popup">
                        <h4>${zone.name}</h4>
                        <p><strong>Risk Threshold:</strong> ${(zone.risk_threshold || 0).toFixed(2)}</p>
                        <p><strong>Manual Override:</strong> ${zone.manual_override_active ? 'Yes' : 'No'}</p>
                        ${zone.manual_override_active && zone.manual_override_until ? 
                            `<p><strong>Override Until:</strong> ${new Date(zone.manual_override_until).toLocaleString()}</p>` : ''}
                    </div>
                `);
            });
        })
        .catch(error => {
            console.error('Error loading zones for full map:', error);
            mapElement.innerHTML = '<div class="map-error">Unable to load flood zones</div>';
        });
}

// Helper function to get color based on risk threshold
function getRiskColor(threshold) {
    if (threshold >= 0.8) return '#ff0000'; // Red - High risk
    if (threshold >= 0.6) return '#ff8000'; // Orange
    if (threshold >= 0.4) return '#ffff00'; // Yellow
    if (threshold >= 0.2) return '#80ff00'; // Light green
    return '#00ff00'; // Green - Low risk
}

// Initialize maps when DOM is loaded
document.addEventListener('DOMContentLoaded', function() {
    initMapPreview();
    initFullMap();
});