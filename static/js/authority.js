// Authority Dashboard JavaScript
function initAuthorityDashboard() {
    // Fetch dashboard statistics
    fetchAuthorityStats();
    
    // Fetch active alerts
    fetchActiveAlerts();
    
    // Fetch pending reports
    fetchPendingReports();
    
    // Fetch flood zones
    fetchFloodZones();
}

// Fetch authority dashboard statistics
function fetchAuthorityStats() {
    // Simulate fetching stats - in real app, these would come from API
    setTimeout(() => {
        document.getElementById('active-alerts-count').textContent = '3';
        document.getElementById('reports-today-count').textContent = '12';
        document.getElementById('pending-reports-count').textContent = '5';
        document.getElementById('verified-today-count').textContent = '8';
    }, 500);
}

// Fetch active alerts for authority dashboard
function fetchActiveAlerts() {
    const alertsContainer = document.getElementById('active-alerts-list');
    
    // Simulate fetching alerts
    setTimeout(() => {
        alertsContainer.innerHTML = `
            <div class="alert-item alert-high">
                <div class="alert-header">
                    <h4>Flood Warning - Zone B</h4>
                    <span class="alert-level high">HIGH</span>
                </div>
                <div class="alert-content">
                    <p>Water levels rising rapidly in the northern districts. Evacuation recommended for low-lying areas.</p>
                    <div class="alert-meta">
                        <span>Issued: 2 hours ago</span>
                        <span>Affects: 5,000 residents</span>
                    </div>
                </div>
                <div class="alert-actions">
                    <button class="btn btn-sm btn-danger">Evacuate Area</button>
                    <button class="btn btn-sm btn-secondary">Send SMS Alert</button>
                </div>
            </div>
            <div class="alert-item alert-medium">
                <div class="alert-header">
                    <h4>Watch Advisory - River Basin</h4>
                    <span class="alert-level medium">MEDIUM</span>
                </div>
                <div class="alert-content">
                    <p>Monitoring increased rainfall in catchment areas. Preparing flood barriers.</p>
                    <div class="alert-meta">
                        <span>Issued: 5 hours ago</span>
                        <span>Affects: 2,000 residents</span>
                    </div>
                </div>
                <div class="alert-actions">
                    <button class="btn btn-sm btn-primary">Deploy Team</button>
                    <button class="btn btn-sm btn-secondary">View Details</button>
                </div>
            </div>
        `;
    }, 800);
}

// Fetch pending reports for review
function fetchPendingReports() {
    const reportsContainer = document.getElementById('pending-reports-list');
    
    // Simulate fetching pending reports
    setTimeout(() => {
        reportsContainer.innerHTML = `
            <div class="report-item">
                <div class="report-header">
                    <h4>Flooding on Main Street</h4>
                    <span class="report-status pending">Pending Review</span>
                </div>
                <div class="report-content">
                    <p><strong>Location:</strong> Main Street & 5th Ave</p>
                    <p><strong>Time:</strong> 2026-05-07 14:30</p>
                    <p><strong>Description:</strong> Water accumulation blocking traffic lane, approximately 15cm deep.</p>
                    <p><strong>Reporter:</strong> Citizen (verified)</p>
                </div>
                <div class="report-actions">
                    <button class="btn btn-sm btn-success">Verify</button>
                    <button class="btn btn-sm btn-warning">Request More Info</button>
                    <button class="btn btn-sm btn-danger">Dismiss</button>
                </div>
            </div>
            <div class="report-item">
                <div class="report-header">
                    <h4>Flash Flood Alert - Hillside Area</h4>
                    <span class="report-status pending">Pending Review</span>
                </div>
                <div class="report-content">
                    <p><strong>Location:</strong> Hillside Residential Area</p>
                    <p><strong>Time:</strong> 2026-05-07 15:15</p>
                    <p><strong>Description:</strong> Sudden water flow downhill after heavy rain, potential mudslide risk.</p>
                    <p><strong>Reporter:</strong> Emergency Team Member</p>
                </div>
                <div class="report-actions">
                    <button class="btn btn-sm btn-success">Verify</button>
                    <button class="btn btn-sm btn-warning">Request More Info</button>
                    <button class="btn btn-sm btn-danger">Dismiss</button>
                </div>
            </div>
        `;
    }, 1000);
}

// Fetch flood zones data
function fetchFloodZones() {
    const zonesContainer = document.getElementById('zones-list');
    
    // Simulate fetching zones
    setTimeout(() => {
        zonesContainer.innerHTML = `
            <div class="zone-item">
                <div class="zone-header">
                    <h4>Zone A - Riverfront District</h4>
                    <span class="zone-risk high">HIGH RISK</span>
                </div>
                <div class="zone-content">
                    <p><strong>Risk Level:</strong> 0.85</p>
                    <p><strong>Monitoring:</strong> Active</p>
                    <p><strong>Last Updated:</strong> 5 minutes ago</p>
                </div>
            </div>
            <div class="zone-item">
                <div class="zone-header">
                    <h4>Zone B - Northern Suburbs</h4>
                    <span class="zone-risk medium">MEDIUM RISK</span>
                </div>
                <div class="zone-content">
                    <p><strong>Risk Level:</strong> 0.62</p>
                    <p><strong>Monitoring:</strong> Active</p>
                    <p><strong>Last Updated:</strong> 10 minutes ago</p>
                </div>
            </div>
            <div class="zone-item">
                <div class="zone-header">
                    <h4>Zone C - Eastern Industrial</h4>
                    <span class="zone-risk low">LOW RISK</span>
                </div>
                <div class="zone-content">
                    <p><strong>Risk Level:</strong> 0.28</p>
                    <p><strong>Monitoring:</strong> Active</p>
                    <p><strong>Last Updated:</strong> 15 minutes ago</p>
                </div>
            </div>
        `;
    }, 1200);
}

// Utility functions for authority dashboard
function formatTimeAgo(dateString) {
    // Same implementation as in dashboard.js
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return `${seconds} seconds ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    if (seconds < 2592000) return `${Math.floor(seconds / 86400)} days ago`;
    
    return date.toLocaleDateString();
}

// Export functions
window.initAuthorityDashboard = initAuthorityDashboard;