// WebSocket connection for real-time alerts
class AlertWebSocket {
    constructor() {
        this.socket = null;
        this.reconnectInterval = 5000; // 5 seconds
        this.maxReconnectAttempts = 10;
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.messageCallbacks = [];
        this.fallbackPolling = null;
        this.useFallback = false;
    }

    connect() {
        if (this.useFallback) {
            this.startPollingFallback();
            return;
        }

        // Determine the WebSocket protocol based on current page protocol
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/alerts/`;
        
        try {
            this.socket = new WebSocket(wsUrl);
            
            this.socket.onopen = () => {
                console.log('WebSocket connected');
                this.isConnected = true;
                this.reconnectAttempts = 0;
                this.onConnect();
            };
            
            this.socket.onmessage = (event) => {
                try {
                    const data = JSON.parse(event.data);
                    this.onMessage(data);
                } catch (e) {
                    console.error('Failed to parse WebSocket message:', e);
                }
            };
            
            this.socket.onclose = (event) => {
                console.log('WebSocket disconnected', event);
                this.isConnected = false;
                this.onDisconnect();
                
                // Attempt to reconnect unless max attempts exceeded
                if (this.reconnectAttempts < this.maxReconnectAttempts) {
                    this.reconnectAttempts++;
                    setTimeout(() => this.connect(), this.reconnectInterval);
                } else {
                    console.warn('Max reconnect attempts reached, switching to polling fallback');
                    this.useFallback = true;
                    this.startPollingFallback();
                }
            };
            
            this.socket.onerror = (error) => {
                console.error('WebSocket error:', error);
                this.onError(error);
            };
        } catch (e) {
            console.error('Failed to create WebSocket:', e);
            this.useFallback = true;
            this.startPollingFallback();
        }
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
        if (this.fallbackPolling) {
            clearInterval(this.fallbackPolling);
        }
    }

    onConnect() {
        this.messageCallbacks.forEach(callback => {
            if (callback.onConnect) callback.onConnect();
        });
    }

    onDisconnect() {
        this.messageCallbacks.forEach(callback => {
            if (callback.onDisconnect) callback.onDisconnect();
        });
    }

    onMessage(data) {
        this.messageCallbacks.forEach(callback => {
            if (callback.onMessage) callback.onMessage(data);
        });
    }

    onError(error) {
        this.messageCallbacks.forEach(callback => {
            if (callback.onError) callback.onError(error);
        });
    }

    registerCallback(callback) {
        this.messageCallbacks.push(callback);
    }

    unregisterCallback(callback) {
        const index = this.messageCallbacks.indexOf(callback);
        if (index > -1) {
            this.messageCallbacks.splice(index, 1);
        }
    }

    startPollingFallback() {
        console.log('Starting HTTP polling fallback for alerts');
        this.fallbackPolling = setInterval(() => {
            fetch('/api/v1/alerts/?limit=5')
                .then(res => res.json())
                .then(data => {
                    const alerts = Array.isArray(data) ? data : (data.results || []);
                    if (alerts.length > 0) {
                        // Send as WebSocket-style message
                        this.onMessage({
                            type: 'alert_batch',
                            alerts: alerts
                        });
                    }
                })
                .catch(err => {
                    console.error('Polling fetch error:', err);
                });
        }, 30000); // Poll every 30 seconds
    }
}

// Global WebSocket instance
const alertWS = new AlertWebSocket();

// Initialize WebSocket connection after the first paint so alerts feel live without blocking render
document.addEventListener('DOMContentLoaded', function() {
    function connectWebSocket() {
        alertWS.connect();
    }

    requestAnimationFrame(() => setTimeout(connectWebSocket, 250));

    // Register UI update callback
    alertWS.registerCallback({
        onMessage: function(data) {
            // Handle incoming alert messages
            updateAlertUI(data);
        }
    });
});

// Function to update UI with new alert data
function updateAlertUI(data) {
    // Handle batch of alerts (from polling fallback)
    if (data.alerts) {
        data.alerts.forEach(alert => {
            showAlertNotification(alert);
        });
        return;
    }
    
    // Handle single alert (from WebSocket)
    showAlertNotification(data);
}

function showAlertNotification(alertData) {
    const message = alertData.message || alertData.zone_name ?
        `${alertData.zone_name}: ${alertData.message || 'Alert issued'}` : 
        'New flood alert received';
    
    const notification = document.createElement('div');
    notification.className = 'alert-notification';
    notification.innerHTML = `
        <div class="alert-content">
            <strong>Flood Alert:</strong> ${escapeHTML(message)}
            <br>
            <small>${new Date().toLocaleTimeString()}</small>
        </div>
    `;
    
    // Prepend to alerts ticker or body
    const ticker = document.querySelector('.alerts-ticker .ticker-track');
    if (ticker) {
        ticker.insertBefore(notification, ticker.firstChild);
        // Keep only last 5 notifications
        const notifications = ticker.querySelectorAll('.alert-notification');
        if (notifications.length > 5) {
            notifications[notifications.length - 1].remove();
        }
    } else {
        document.body.appendChild(notification);
    }
    
    // Remove after 8 seconds
    setTimeout(() => {
        notification.remove();
    }, 8000);
    
    // Also update any dashboard elements if present
    updateDashboardAlerts();
}

// Function to update dashboard alerts (if on dashboard page)
function updateDashboardAlerts() {
    // This would typically fetch fresh data from API
    // For now, we'll just indicate that new data is available
    const dashboardElements = document.querySelectorAll('[data-alerts-count]');
    dashboardElements.forEach(el => {
        const currentCount = parseInt(el.textContent) || 0;
        el.textContent = currentCount + 1;
        el.style.backgroundColor = '#ffebee';
        el.style.color = '#c62828';
        
        // Reset color after 2 seconds
        setTimeout(() => {
            el.style.backgroundColor = '';
            el.style.color = '';
        }, 2000);
    });
}

// Export for use in other modules
window.alertWS = alertWS;
