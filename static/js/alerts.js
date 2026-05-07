// WebSocket connection for real-time alerts
class AlertWebSocket {
    constructor() {
        this.socket = null;
        this.reconnectInterval = 5000; // 5 seconds
        this.maxReconnectAttempts = 10;
        this.reconnectAttempts = 0;
        this.isConnected = false;
        this.messageCallbacks = [];
    }

    connect() {
        // Determine the WebSocket protocol based on current page protocol
        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
        const wsUrl = `${protocol}//${window.location.host}/ws/alerts/`;
        
        this.socket = new WebSocket(wsUrl);
        
        this.socket.onopen = () => {
            console.log('WebSocket connected');
            this.isConnected = true;
            this.reconnectAttempts = 0;
            this.onConnect();
        };
        
        this.socket.onmessage = (event) => {
            const data = JSON.parse(event.data);
            this.onMessage(data);
        };
        
        this.socket.onclose = (event) => {
            console.log('WebSocket disconnected', event);
            this.isConnected = false;
            this.onDisconnect();
            
            // Attempt to reconnect
            if (this.reconnectAttempts < this.maxReconnectAttempts) {
                this.reconnectAttempts++;
                setTimeout(() => this.connect(), this.reconnectInterval);
            }
        };
        
        this.socket.onerror = (error) => {
            console.error('WebSocket error:', error);
            this.onError(error);
        };
    }

    disconnect() {
        if (this.socket) {
            this.socket.close();
        }
    }

    onConnect() {
        // Override this method in subclasses or set callback
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

    // Register a callback for WebSocket events
    registerCallback(callback) {
        this.messageCallbacks.push(callback);
    }

    // Unregister a callback
    unregisterCallback(callback) {
        const index = this.messageCallbacks.indexOf(callback);
        if (index > -1) {
            this.messageCallbacks.splice(index, 1);
        }
    }
}

// Global WebSocket instance
const alertWS = new AlertWebSocket();

// Initialize WebSocket connection when DOM loads
document.addEventListener('DOMContentLoaded', function() {
    alertWS.connect();
    
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
    // Create a notification element
    const notification = document.createElement('div');
    notification.className = 'alert-notification';
    notification.innerHTML = `
        <div class="alert-content">
            <strong>New Flood Alert:</strong> ${data.message || 'Alert received'}
            <br>
            <small>${new Date().toLocaleTimeString()}</small>
        </div>
    `;
    
    // Add to page (you might want to customize where this appears)
    document.body.appendChild(notification);
    
    // Remove after 5 seconds
    setTimeout(() => {
        notification.remove();
    }, 5000);
    
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