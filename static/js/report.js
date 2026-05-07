// Report submission form JavaScript
function initReportForm() {
    // Initialize form elements
    const form = document.getElementById('report-form');
    const locationStatusIcon = document.getElementById('location-icon');
    const locationStatusText = document.getElementById('location-text');
    const latitudeInput = document.getElementById('latitude');
    const longitudeInput = document.getElementById('longitude');
    const accuracyInput = document.getElementById('accuracy');
    const accuracyValue = document.getElementById('accuracy-value');
    const useCurrentLocationBtn = document.getElementById('use-current-location');
    const submitBtn = document.getElementById('submit-btn');
    
    // Initialize manual map
    initManualMap();
    
    // Handle use current location button
    if (useCurrentLocationBtn) {
        useCurrentLocationBtn.addEventListener('click', getCurrentLocation);
    }
    
    // Handle form submission
    if (form) {
        form.addEventListener('submit', function(e) {
            e.preventDefault();
            submitReport(form);
        });
    }
    
    // Try to get current location on page load
    getCurrentLocation();
}

// Get current location using Geolocation API
function getCurrentLocation() {
    if (!navigator.geolocation) {
        updateLocationStatus('Geolocation is not supported by your browser', false);
        return;
    }
    
    updateLocationStatus('Detecting your location...', true);
    
    navigator.geolocation.getCurrentPosition(
        position => {
            const { latitude, longitude, accuracy } = position.coords;
            
            // Update form fields
            document.getElementById('latitude').value = latitude.toFixed(6);
            document.getElementById('longitude').value = longitude.toFixed(6);
            document.getElementById('accuracy').value = accuracy.toFixed(0);
            document.getElementById('accuracy-value').textContent = `${accuracy.toFixed(0)} meters`;
            
            // Update status
            updateLocationStatus('Location detected successfully!', true);
            
            // If manual map exists, set view to current location
            if (window.manualMap) {
                window.manualMap.setView([latitude, longitude], 15);
                
                // Remove any existing marker and add new one
                if (window.userLocationMarker) {
                    window.manualMap.removeLayer(window.userLocationMarker);
                }
                window.userLocationMarker = L.marker([latitude, longitude]).addTo(window.manualMap)
                    .bindPopup('Your Location')
                    .openPopup();
            }
        },
        error => {
            let message = 'Unable to detect your location';
            switch(error.code) {
                case error.PERMISSION_DENIED:
                    message = 'Location access denied. Please enable location services or enter coordinates manually.';
                    break;
                case error.POSITION_UNAVAILABLE:
                    message = 'Location information unavailable. Please enter coordinates manually.';
                    break;
                case error.TIMEOUT:
                    message = 'Location request timed out. Please enter coordinates manually.';
                    break;
                default:
                    message = 'An unknown error occurred while detecting location.';
                    break;
            }
            updateLocationStatus(message, false);
        },
        {
            enableHighAccuracy: true,
            timeout: 10000,
            maximumAge: 0
        }
    );
}

// Update location status UI
function updateLocationStatus(message, isSuccess) {
    const statusIcon = document.getElementById('location-icon');
    const statusText = document.getElementById('location-text');
    
    statusText.textContent = message;
    
    if (isSuccess) {
        statusIcon.textContent = '✅';
        statusIcon.style.color = '#2ecc71';
    } else {
        statusIcon.textContent = '❌';
        statusIcon.style.color = '#e74c3c';
    }
}

// Initialize manual override map
function initManualMap() {
    const manualMapElement = document.getElementById('manual-map');
    if (!manualMapElement) return;
    
    // Initialize map
    const map = L.map('manual-map').setView([0, 0], 2);
    
    // Add tile layer
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '&copy; <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors'
    }).addTo(map);
    
    // Store map instance globally for access
    window.manualMap = map;
    
    // Add click event to set marker
    map.on('click', function(e) {
        const { lat, lng } = e.latlng;
        
        // Update form fields
        document.getElementById('manual-latitude').value = lat.toFixed(6);
        document.getElementById('manual-longitude').value = lng.toFixed(6);
        
        // Remove existing marker and add new one
        if (window.manualMarker) {
            map.removeLayer(window.manualMarker);
        }
        window.manualMarker = L.marker([lat, lng]).addTo(map)
            .bindPopup('Selected Location')
            .openPopup();
    });
    
    // Try to set initial view to user location if available
    if (navigator.geolocation) {
        navigator.geolocation.getCurrentPosition(
            position => {
                const { latitude, longitude } = position.coords;
                map.setView([latitude, longitude], 15);
            },
            () => {
                // Default to Nairobi if geolocation fails
                map.setView([-1.2921, 36.8219], 10);
            }
        );
    } else {
        // Default to Nairobi
        map.setView([-1.2921, 36.8219], 10);
    }
}

// Submit report via AJAX
function submitReport(form) {
    const submitBtn = document.getElementById('submit-btn');
    const formData = new FormData(form);
    
    // Disable submit button and show loading state
    submitBtn.disabled = true;
    submitBtn.innerHTML = '<span class="spinner"></span> Submitting...';
    
    // Create a spinner element if not exists
    if (!document.querySelector('#submit-spinner-style')) {
        const style = document.createElement('style');
        style.id = 'submit-spinner-style';
        style.textContent = `
            .spinner {
                display: inline-block;
                width: 16px;
                height: 16px;
                border: 2px solid #fff;
                border-top-color: transparent;
                border-radius: 50%;
                animation: spin 0.8s linear infinite;
                margin-right: 8px;
            }
            @keyframes spin {
                to { transform: rotate(360deg); }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Submit via fetch
    fetch(form.action, {
        method: 'POST',
        body: formData,
        headers: {
            // Note: Django CSRF token is handled by FormData
            // 'X-CSRFToken': getCookie('csrftoken') // Alternative if not using FormData
        }
    })
    .then(response => {
        if (!response.ok) {
            throw new Error(`HTTP error! status: ${response.status}`);
        }
        return response.json();
    })
    .then(data => {
        if (data.success) {
            // Show success message and redirect or update UI
            showNotification('Report submitted successfully!', 'success');
            
            // Redirect to report list or show success view
            setTimeout(() => {
                window.location.href = '{% url \'report_list\' %}';
            }, 1500);
        } else {
            throw new Error(data.error || 'Unknown error occurred');
        }
    })
    .catch(error => {
        console.error('Error submitting report:', error);
        showNotification(`Error: ${error.message}`, 'error');
        
        // Re-enable submit button
        submitBtn.disabled = false;
        submitBtn.textContent = 'Submit Report';
    });
}

// Show notification function (reuse from main.js if available, otherwise define here)
function showNotification(message, type = 'info', duration = 3000) {
    // Remove any existing notifications
    const existingNotifications = document.querySelectorAll('.notification');
    existingNotifications.forEach(el => el.remove());
    
    // Create notification element
    const notification = document.createElement('div');
    notification.className = `notification notification-${type}`;
    notification.innerHTML = `
        <div class="notification-content">
            ${message}
        </div>
        <button class="notification-close">&times;</button>
    `;
    
    // Add styles if not already present
    if (!document.querySelector('#notification-styles')) {
        const style = document.createElement('style');
        style.id = 'notification-styles';
        style.textContent = `
            .notification {
                position: fixed;
                top: 20px;
                right: 20px;
                padding: 15px 20px;
                border-radius: 4px;
                color: white;
                display: flex;
                justify-content: space-between;
                align-items: center;
                z-index: 1000;
                box-shadow: 0 4px 12px rgba(0,0,0,0.15);
                animation: slideIn 0.3s ease-out;
            }
            
            .notification-info { background-color: #3498db; }
            .notification-success { background-color: #2ecc71; }
            .notification-warning { background-color: #f39c12; }
            .notification-error { background-color: #e74c3c; }
            
            .notification-content {
                flex: 1;
                margin-right: 10px;
            }
            
            .notification-close {
                background: none;
                border: none;
                color: white;
                font-size: 1.2rem;
                cursor: pointer;
                width: 30px;
                height: 30px;
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            @keyframes slideIn {
                from {
                    transform: translateX(100%);
                    opacity: 0;
                }
                to {
                    transform: translateX(0);
                    opacity: 1;
                }
            }
            
            @keyframes slideOut {
                from {
                    transform: translateX(0);
                    opacity: 1;
                }
                to {
                    transform: translateX(100%);
                    opacity: 0;
                }
            }
        `;
        document.head.appendChild(style);
    }
    
    // Add to page
    document.body.appendChild(notification);
    
    // Remove on close button click
    const closeBtn = notification.querySelector('.notification-close');
    closeBtn.addEventListener('click', function() {
        notification.style.animation = 'slideOut 0.3s ease-in';
        setTimeout(() => notification.remove(), 300);
    });
    
    // Auto remove after duration
    setTimeout(() => {
        if (notification.parentNode) {
            notification.style.animation = 'slideOut 0.3s ease-in';
            setTimeout(() => notification.remove(), 300);
        }
    }, duration);
}

// Helper function to get cookie (if needed for CSRF)
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

// Export functions for use in other files
window.initReportForm = initReportForm;
window.getCurrentLocation = getCurrentLocation;