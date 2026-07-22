(function() {
    'use strict';

    const NAIROBI = { lat: -1.2921, lon: 36.8219, zoom: 12 };
    const STORAGE_KEY = 'fg_last_location';
    const CACHE_TTL = 5 * 60 * 1000;

    let _current = null;
    let _callbacks = [];
    let _status = 'idle';

    function _save(loc) {
        try {
            localStorage.setItem(STORAGE_KEY, JSON.stringify(loc));
        } catch(_) {}
    }

    function _restore() {
        try {
            const raw = localStorage.getItem(STORAGE_KEY);
            if (!raw) return null;
            const loc = JSON.parse(raw);
            const age = Date.now() - (loc.ts || 0);
            return age < CACHE_TTL ? loc : null;
        } catch(_) { return null; }
    }

    function _notify(loc, isReal) {
        _callbacks.forEach(cb => {
            try { cb(loc, isReal); } catch(_) {}
        });
    }

    function _showStatus(msg, colour, autohide) {
        let el = document.getElementById('fg-location-status');
        if (!el) {
            el = document.createElement('div');
            el.id = 'fg-location-status';
            el.style.cssText = [
                'position:fixed','bottom:80px','left:50%',
                'transform:translateX(-50%)','z-index:9999',
                'padding:10px 20px','border-radius:20px',
                'font-size:13px','font-weight:600','color:#fff',
                'pointer-events:none','transition:opacity 0.3s',
                'white-space:nowrap','display:none',
            ].join(';');
            document.body.appendChild(el);
        }
        el.textContent = msg;
        el.style.background = colour || '#0A2540';
        el.style.display = 'block';
        el.style.opacity = '1';
        if (autohide) {
            setTimeout(() => {
                el.style.opacity = '0';
                setTimeout(() => el.style.display = 'none', 300);
            }, autohide);
        }
    }

    function _useFallback(reason) {
        console.info('[FloodLocation] Fallback:', reason);
        _status = 'fallback';
        const cached = _restore();
        const loc = cached || { ...NAIROBI, accuracy: null, source: 'default', ts: Date.now() };
        _current = loc;
        _notify(loc, false);
        const msg = cached ? '📍 Using last known location' : '📍 Nairobi (default) — allow location for local data';
        _showStatus(msg, '#64748B', 4000);
    }

    function _request() {
        if (!('geolocation' in navigator)) {
            _useFallback('API not available');
            return;
        }
        _status = 'requesting';
        _showStatus('📍 Detecting your location...', '#0A2540');
        const cached = _restore();
        if (cached) {
            _current = cached;
            _notify(cached, true);
            _showStatus('📍 Location found', '#059669', 2000);
        }
        navigator.geolocation.getCurrentPosition(
            function(pos) {
                const loc = {
                    lat: pos.coords.latitude,
                    lon: pos.coords.longitude,
                    accuracy: pos.coords.accuracy,
                    source: 'gps',
                    ts: Date.now(),
                    zoom: pos.coords.accuracy < 500 ? 15 : 13,
                };
                if (!loc.lat || !loc.lon || loc.lat === 0 || loc.lon === 0) {
                    _useFallback('Invalid coordinates');
                    return;
                }
                _current = loc;
                _status = 'granted';
                _save(loc);
                _notify(loc, true);
                _showStatus('📍 Location detected', '#059669', 2000);
            },
            function(err) {
                const msgs = { 1: 'Permission denied', 2: 'Position unavailable', 3: 'Request timed out' };
                _useFallback(msgs[err.code] || 'Unknown error');
            },
            { enableHighAccuracy: true, timeout: 8000, maximumAge: 60000 }
        );
    }

    function _ipFallback() {
        fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout ? AbortSignal.timeout(5000) : undefined })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (data && data.latitude && data.longitude) {
                    const loc = {
                        lat: parseFloat(data.latitude),
                        lon: parseFloat(data.longitude),
                        accuracy: 10000,
                        source: 'ip',
                        ts: Date.now(),
                        zoom: 11,
                        city: data.city || '',
                        country: data.country_name || '',
                    };
                    _current = loc;
                    _save(loc);
                    _notify(loc, true);
                    _showStatus(`📍 ${loc.city || 'Your city'} (IP location)`, '#D97706', 3000);
                } else {
                    _useFallback('IP lookup empty');
                }
            })
            .catch(() => _useFallback('IP lookup failed'));
    }

    window.FloodLocation = {
        on: function(fn) {
            _callbacks.push(fn);
            if (_current) fn(_current, _status === 'granted');
        },
        off: function(fn) {
            _callbacks = _callbacks.filter(cb => cb !== fn);
        },
        detect: function(strategy) {
            strategy = strategy || 'auto';
            if (strategy === 'ip') {
                _ipFallback();
            } else {
                _request();
                setTimeout(() => {
                    if (_status === 'denied' || _status === 'fallback') {
                        _ipFallback();
                    }
                }, 10000);
            }
        },
        get current() { return _current; },
        get status() { return _status; },
        get default() { return NAIROBI; },
        refresh: function() {
            _status = 'idle';
            _request();
        },
    };
})();