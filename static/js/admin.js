// Admin Dashboard JavaScript
function initAdminDashboard() {
    // Fetch dashboard statistics
    fetchAdminStats();
    
    // Fetch system overview data
    fetchSystemOverview();
    
    // Fetch recent system activity
    fetchSystemActivity();
}

// Fetch admin dashboard statistics
function fetchAdminStats() {
    // Simulate fetching stats - in real app, these would come from API
    setTimeout(() => {
        document.getElementById('total-users-count').textContent = '1,245';
        document.getElementById('active-alerts-count').textContent = '3';
        document.getElementById('total-reports-count').textContent = '892';
        document.getElementById('system-health').textContent = '98%';
    }, 500);
}

// Fetch system overview data
function fetchSystemOverview() {
    // Users by role chart placeholder
    const usersByRoleChart = document.getElementById('users-by-role-chart');
    if (usersByRoleChart) {
        usersByRoleChart.innerHTML = `
            <div class="chart-content">
                <div class="chart-bar">
                    <div class="chart-label">Citizens</div>
                    <div class="chart-value">1,024 (82%)</div>
                    <div class="chart-bar-fill" style="width: 82%; background-color: #3498db;"></div>
                </div>
                <div class="chart-bar">
                    <div class="chart-label">Emergency Team</div>
                    <div class="chart-value">187 (15%)</div>
                    <div class="chart-bar-fill" style="width: 15%; background-color: #e67e22;"></div>
                </div>
                <div class="chart-bar">
                    <div class="chart-label">Administrators</div>
                    <div class="chart-value">34 (3%)</div>
                    <div class="chart-bar-fill" style="width: 3%; background-color: #9b59b6;"></div>
                </div>
            </div>
        `;
    }
    
    // Alerts by channel chart placeholder
    const alertsByChannelChart = document.getElementById('alerts-by-channel-chart');
    if (alertsByChannelChart) {
        alertsByChannelChart.innerHTML = `
            <div class="chart-content">
                <div class="chart-bar">
                    <div class="chart-label">WebSocket</div>
                    <div class="chart-value">456 (51%)</div>
                    <div class="chart-bar-fill" style="width: 51%; background-color: #2ecc71;"></div>
                </div>
                <div class="chart-bar">
                    <div class="chart-label">SMS</div>
                    <div class="chart-value">298 (33%)</div>
                    <div class="chart-bar-fill" style="width: 33%; background-color: #3498db;"></div>
                </div>
                <div class="chart-bar">
                    <div class="chart-label">Email</div>
                    <div class="chart-value">138 (16%)</div>
                    <div class="chart-bar-fill" style="width: 16%; background-color: #e74c3c;"></div>
                </div>
            </div>
        `;
    }
    
    // Reports trend chart placeholder
    const reportsTrendChart = document.getElementById('reports-trend-chart');
    if (reportsTrendChart) {
        reportsTrendChart.innerHTML = `
            <div class="chart-content">
                <div class="chart-line">
                    <div class="chart-point" style="left: 0%; bottom: 20%;"></div>
                    <div class="chart-point" style="left: 16.6%; bottom: 35%;"></div>
                    <div class="chart-point" style="left: 33.3%; bottom: 50%;"></div>
                    <div class="chart-point" style="left: 50%; bottom: 65%;"></div>
                    <div class="chart-point" style="left: 66.6%; bottom: 45%;"></div>
                    <div class="chart-point" style="left: 83.3%; bottom: 60%;"></div>
                    <div class="chart-point" style="left: 100%; bottom: 75%;"></div>
                </div>
                <div class="chart-axis">
                    <div class="chart-axis-label">7 Days Trend</div>
                </div>
            </div>
        `;
    }
    
    // Zone status list
    const zoneStatusList = document.getElementById('zone-status-list');
    if (zoneStatusList) {
        zoneStatusList.innerHTML = `
            <div class="zone-status-item">
                <div class="zone-status-header">
                    <h4>Zone A - Riverfront District</h4>
                    <span class="zone-status-risk high">HIGH</span>
                </div>
                <div class="zone-status-content">
                    <p><strong>Risk Level:</strong> 0.85</p>
                    <p><strong>Last Reading:</strong> 2 minutes ago</p>
                    <p><strong>Status:</strong> Monitoring Active</p>
                </div>
            </div>
            <div class="zone-status-item">
                <div class="zone-status-header">
                    <h4>Zone B - Northern Suburbs</h4>
                    <span class="zone-status-risk medium">MEDIUM</span>
                </div>
                <div class="zone-status-content">
                    <p><strong>Risk Level:</strong> 0.62</p>
                    <p><strong>Last Reading:</strong> 5 minutes ago</p>
                    <p><strong>Status:</strong> Monitoring Active</p>
                </div>
            </div>
            <div class="zone-status-item">
                <div class="zone-status-header">
                    <h4>Zone C - Eastern Industrial</h4>
                    <span class="zone-status-risk low">LOW</span>
                </div>
                <div class="zone-status-content">
                    <p><strong>Risk Level:</strong> 0.28</p>
                    <p><strong>Last Reading:</strong> 1 minute ago</p>
                    <p><strong>Status:</strong> Monitoring Active</p>
                </div>
            </div>
            <div class="zone-status-item">
                <div class="zone-status-header">
                    <h4>Zone D - Western Hills</h4>
                    <span class="zone-status-risk high">HIGH</span>
                    <span class="zone-status-override">OVERRIDE</span>
                </div>
                <div class="zone-status-content">
                    <p><strong>Risk Level:</strong> 0.91</p>
                    <p><strong>Last Reading:</strong> 3 minutes ago</p>
                    <p><strong>Status:</strong> Manual Override Active</p>
                </div>
            </div>
        `;
    }
}

// Fetch recent system activity
function fetchSystemActivity() {
    const timeline = document.getElementById('system-activity-timeline');
    
    // Simulate fetching activity
    setTimeout(() => {
        timeline.innerHTML = `
            <div class="activity-item">
                <div class="activity-icon">👤</div>
                <div class="activity-content">
                    <h4>New User Registration</h4>
                    <p>Citizen account created: john.doe@email.com</p>
                    <time datetime="2026-05-07T16:45:00">Just now</time>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-icon">📊</div>
                <div class="activity-content">
                    <h4>Model Retraining Completed</h4>
                    <p>Flood prediction model updated with latest data</p>
                    <time datetime="2026-05-07T16:30:00">15 minutes ago</time>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-icon">🔧</div>
                <div class="activity-content">
                    <h4>System Backup</h4>
                    <p>Daily database backup completed successfully</p>
                    <time datetime="2026-05-07T02:00:00">Today at 2:00 AM</time>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-icon">🚨</div>
                <div class="activity-content">
                    <h4>Alert Issued</h4>
                    <p>Flood warning for Zone B - Northern Suburbs</p>
                    <time datetime="2026-05-07T15:20:00">1 hour ago</time>
                </div>
            </div>
            <div class="activity-item">
                <div class="activity-icon">✅</div>
                <div class="activity-content">
                    <h4>Report Verified</h4>
                    <p>Incident on Main Street confirmed by emergency team</p>
                    <time datetime="2026-05-07T14:15:00">2 hours ago</time>
                </div>
            </div>
        `;
    }, 1000);
}

// Utility functions for admin dashboard
function formatTimeAgo(dateString) {
    // Same implementation as in other dashboard files
    const date = new Date(dateString);
    const now = new Date();
    const seconds = Math.floor((now - date) / 1000);
    
    if (seconds < 60) return `${seconds} seconds ago`;
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    if (seconds < 2592000) return `${Math.floor(seconds / 86400)} days ago`;
    
    return date.toLocaleDateString();
}

// Chart utility functions (would be expanded with actual charting library in production)
function renderChartPlaceholder(element, type, data) {
    // This would be replaced with actual charting library like Chart.js
    // For now, we'll just show placeholder content
    element.innerHTML = `<div class="chart-placeholder">Chart: ${type}</div>`;
}

// Export functions
window.initAdminDashboard = initAdminDashboard;