function initReportForm() {
    const form = document.getElementById('report-form');
    if (!form) return;

    const severity = document.getElementById('severity');
    const severityValue = document.getElementById('severity-value');
    const photo = document.getElementById('photo');
    const photoLabel = document.getElementById('photo-label');
    const photoPreview = document.getElementById('photo-preview');
    const gpsButton = document.getElementById('use-current-location');

    function syncSeverity() {
        const value = Number(severity.value);
        severityValue.textContent = value;
        const colour = value <= 2 ? '#059669' : value === 3 ? '#D97706' : '#DC2626';
        severity.style.accentColor = colour;
    }

    severity.addEventListener('input', syncSeverity);
    syncSeverity();

    photo.addEventListener('change', () => {
        const file = photo.files[0];
        if (!file) return;
        photoLabel.textContent = file.name;
        photoPreview.src = URL.createObjectURL(file);
        photoPreview.hidden = false;
    });

    gpsButton.addEventListener('click', getCurrentLocation);

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        const submitBtn = this.querySelector('[type=submit]');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> Submitting...';

        const formData = new FormData(this);
        if (window._reportLat) formData.set('latitude', window._reportLat);
        if (window._reportLon) formData.set('longitude', window._reportLon);

        try {
            const res = await fetch('/api/v1/reports/', {
                method: 'POST',
                headers: { 'X-CSRFToken': getCookie('csrftoken') },
                body: formData
            });
            if (res.ok) {
                showSuccessState();
            } else {
                const errors = await res.json();
                showFormErrors(errors);
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Report';
            }
        } catch (err) {
            showFormErrors({ non_field_errors: ['Network error. Please try again.'] });
            submitBtn.disabled = false;
            submitBtn.textContent = 'Submit Report';
        }
    });
}

function getCurrentLocation() {
    const button = document.getElementById('use-current-location');
    if (!button) return;
    const label = button.querySelector('.gps-label') || button;
    const resetButton = () => {
        button.disabled = false;
        label.textContent = 'Use Current Location';
    };

    if (!navigator.geolocation) {
        updateLocationStatus('Geolocation is not supported by this browser.', false);
        resetButton();
        return;
    }

    button.disabled = true;
    label.textContent = 'Locating...';
    navigator.geolocation.getCurrentPosition(pos => {
        const { latitude, longitude, accuracy } = pos.coords;
        window._reportLat = latitude;
        window._reportLon = longitude;
        document.getElementById('latitude').value = latitude.toFixed(6);
        document.getElementById('longitude').value = longitude.toFixed(6);
        updateLocationStatus(`Location set within ${Math.round(accuracy)} metres.`, true);
        label.textContent = 'Refresh Current Location';
        button.disabled = false;
    }, (error) => {
        const messages = {
            1: 'Location permission denied. Enter coordinates manually.',
            2: 'Location unavailable. Enter coordinates manually.',
            3: 'Location request timed out. Try again or enter coordinates manually.'
        };
        updateLocationStatus(messages[error && error.code] || 'Location unavailable. Enter coordinates manually.', false);
        resetButton();
    }, {
        enableHighAccuracy: true,
        timeout: 10000,
        maximumAge: 0
    });
}

function updateLocationStatus(message, isSuccess) {
    const icon = document.getElementById('location-icon');
    const text = document.getElementById('location-text');
    if (icon) {
        icon.textContent = '●';
        icon.style.color = isSuccess ? '#059669' : '#DC2626';
    }
    if (text) text.textContent = message;
}

function showFormErrors(errors) {
    const box = document.getElementById('form-errors');
    const messages = [];
    Object.keys(errors || {}).forEach(key => {
        const value = Array.isArray(errors[key]) ? errors[key].join(', ') : errors[key];
        messages.push(`${key}: ${value}`);
    });
    box.textContent = messages.join(' ');
}

function showSuccessState() {
    const form = document.getElementById('report-form');
    form.outerHTML = `
        <div class="report-form card success-state">
            <div class="success-check">✓</div>
            <h2 class="section-title">Thank you</h2>
            <p class="section-subtitle">Your report has been submitted.</p>
            <a class="btn btn-primary" href="/reports/">View Reports</a>
        </div>
    `;
}

window.initReportForm = initReportForm;
window.getCurrentLocation = getCurrentLocation;
