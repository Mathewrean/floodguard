function initReportForm() {
    const form = document.getElementById('report-form');
    if (!form) return;

    const severity = document.getElementById('severity');
    const severityValue = document.getElementById('severity-value');
    const photo = document.getElementById('photo');
    const photoLabel = document.getElementById('photo-label');
    const photoPreview = document.getElementById('photo-preview');
    const gpsButton = document.getElementById('use-current-location');

    setReportLocation(-1.2921, 36.8219);
    updateLocationStatus('Default location set to Nairobi.', true);

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

    gpsButton.addEventListener('click', () => {
        const loc = FloodLocation.current;
        if (loc) {
            setReportLocation(loc.lat, loc.lon);
        } else {
            FloodLocation.on((l) => setReportLocation(l.lat, l.lon));
            FloodLocation.detect('auto');
        }
    });

    form.addEventListener('submit', async function(e) {
        e.preventDefault();
        const submitBtn = this.querySelector('[type=submit]');
        submitBtn.disabled = true;
        submitBtn.innerHTML = '<span class="spinner"></span> Submitting...';

        const formData = new FormData(this);
        const loc = FloodLocation.current;
        if (loc) {
            formData.set('latitude', loc.lat);
            formData.set('longitude', loc.lon);
        }

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
            if (!navigator.onLine) {
                const data = {};
                formData.forEach((v, k) => data[k] = v);
                await OfflineStore.savePendingReport(data);
                showSuccessState('Report saved offline — will sync when connected');
            } else {
                showFormErrors({ non_field_errors: ['Network error. Please try again.'] });
                submitBtn.disabled = false;
                submitBtn.textContent = 'Submit Report';
            }
        }
    });
}

function setReportLocation(latitude, longitude) {
    window._reportLat = latitude;
    window._reportLon = longitude;
    const latInput = document.getElementById('latitude');
    const lonInput = document.getElementById('longitude');
    if (latInput) latInput.value = Number(latitude).toFixed(6);
    if (lonInput) lonInput.value = Number(longitude).toFixed(6);
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

function showSuccessState(message) {
    const form = document.getElementById('report-form');
    const msg = message || 'Your report has been submitted.';
    form.outerHTML = `
        <div class="report-form card success-state">
            <div class="success-check">✓</div>
            <h2 class="section-title">Thank you</h2>
            <p class="section-subtitle">${message || 'Your report has been submitted.'}</p>
            <a class="btn btn-primary" href="/reports/">View Reports</a>
        </div>
    `;
}

window.initReportForm = initReportForm;
