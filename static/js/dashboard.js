// Dashboard JavaScript for citizen dashboard
function initCitizenDashboard() {
    // Fetch dashboard statistics
    fetchDashboardStats();
    
    // Fetch recent activity
    fetchRecentActivity();
    
    // Initialize nearby reports map
    initReportsMap();
}

// Fetch dashboard statistics from API
function fetchDashboardStats() {
    // In a real implementation, these would come from API endpoints
    // For now, we'll simulate with placeholder data or fetch from actual endpoints
    
    // Simulate fetching stats
    setTimeout(() => {
        document.getElementById('my-reports-count').textContent = '5';
        document.getElementById('active-alerts-count').textContent = '2';
        document.getElementById('verified-reports-count').textContent = '3';
        document.getElementById('safety-score').textContent = '78';
    }, 500);
}

// Fetch recent activity from API
function fetchRecentActivity() {
    const timeline = document.getElementById('activity-timeline');
    
    // Simulate fetching activity
    setTimeout(() => {
        timeline.innerHTML = `
            <div class="activity-item">
                <div class="activity-icon">📝</div>
                <div class="activity-content">
                    <h4>Flood report submitted</h4>
                    <p>You reported flooding in downtown area</p>
                    <time datetime="2026-05-07T10:30:00">2 hours ago</time>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-icon">✅</div>
                <div class="activity-content">
                    <h4>Report verified</h4>
                    <p>Your report on River Street has been verified by authorities</p>
                    <time datetime="2026-05-07T08:15:00">Yesterday</time>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-icon">🚨</div>
                <div class="activity-content">
                    <h4>New alert issued</h4>
                    <p>Flood warning for your area (Zone B)</p>
                    <time datetime="2026-05-07T06:45:00">Yesterday</time>
                </div>
            </div>
        `;
    }, 800);
}

// Initialize reports map
function initReportsMap() {
    const mapElement = document.getElementById('reports-map');
    if (!mapElement) return;
    
    // Initialize Leaflet map
    const map = L.map('reports-map').setView([0, 0], 2);
    
    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Add sample markers for nearby reports
    // In a real app, these would come from an API
    const sampleReports = [
        { lat: -1.28, lng: 36.82, title: "Flooding reported", time: "2 hours ago" },
        { lat: -1.31, lng: 36.80, title: "Water levels rising", time: "5 hours ago" },
        { lat: -1.25, lng: 36.85, title: "Road closed due to flood", time: "1 day ago" }
    ];
    
    sampleReports.forEach(report => {
        const marker = L.circleMarker([report.lat, report.lng], {
            radius: 6,
            fillColor: '#e74c3c',
            color: '#fff',
            weight: 1,
            opacity: 1,
            fillOpacity: 0.7
        }).addTo(map);
        
        marker.bindPopup(`
            <b>${report.title}</b><br>
            <small>${report.time}</small>
        `);
    });
    
    // Try to get user location and center map
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => {
                const userLat = position.coords.latitude;
                const userLng = position.coords.longitude;
                map.setView([userLat, userLng], 13);
                
                // Add user location marker
                L.marker([userLat, userLng], {
                    icon: L.divIcon({
                        className: 'user-location-icon',
                        html: '👤',
                        iconSize: [30, 30]
                    })
                }).addTo(map)
                .bindPopup('Your Location')
                .openPopup();
            },
            error => {
                console.warn('Geolocation not available:', error);
                // Default to Nairobi if geolocation fails
                map.setView([-1.2921, 36.8219], 10);
            }
        );
    } else {
        // Default to Nairobi if geolocation not supported
        map.setView([-1.2921, 36.8219], 10);
    }
}

// Utility function to format time ago
function timeAgo(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return `${seconds} seconds ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    if (seconds < 2592000) return `${Math.floor(seconds / 86400)} days ago`;
    
    return date.toLocaleDateString();
}

// Export functions for use in other files
window.initCitizenDashboard = initCitizenDashboard;