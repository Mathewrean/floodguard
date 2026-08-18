(function() {
    'use strict';

    const NAIROBI = { lat: -1.2921, lon: 36.8219, zoom: 12 };
    const STORAGE_KEY = 'fg_last_location';
    const CACHE_TTL = 30 * 1000;
    const MAX_ACCURACY = 100;
    const RETRY_LIMIT = 3;
    const GPS_TIMEOUT = 30000;
    const WATCH_TIMEOUT = 15000;

    let _current = null;
    let _callbacks = [];
    let _status = 'idle';
    let _watchId = null;
    let _retryCount = 0;
    let _bestReading = null;
    let _locationQuality = 0;
    let _source = 'default';

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

    function _clearCache() {
        try {
            localStorage.removeItem(STORAGE_KEY);
        } catch(_) {}
    }

    function _notify(loc, isReal) {
        _callbacks.forEach(cb => {
            try { cb(loc, isReal); } catch(_) {}
        });
    }

    function _calculateQuality(loc) {
        if (!loc) return 0;
        const acc = loc.accuracy || 9999;
        const age = Date.now() - (loc.ts || 0);
        const ageSec = age / 1000;
        let score = 100;

        if (acc <= 5) score = 98;
        else if (acc <= 10) score = 95;
        else if (acc <= 20) score = 90;
        else if (acc <= 50) score = 80;
        else if (acc <= 100) score = 65;
        else if (acc <= 500) score = 40;
        else score = 20;

        if (ageSec > 30) score -= 30;
        else if (ageSec > 10) score -= 15;
        else if (ageSec > 5) score -= 5;

        score = Math.max(0, Math.min(100, score));
        return Math.round(score);
    }

    function _qualityLabel(score) {
        if (score >= 90) return 'Excellent';
        if (score >= 75) return 'Good';
        if (score >= 50) return 'Moderate';
        if (score >= 25) return 'Poor';
        return 'Very Poor';
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
        el.style.background = colour || '#1677C8';
        el.style.display = 'block';
        el.style.opacity = '1';
        if (autohide) {
            setTimeout(() => {
                el.style.opacity = '0';
                setTimeout(() => el.style.display = 'none', 300);
            }, autohide);
        }
    }

    function _validateCoordinates(lat, lon) {
        if (typeof lat !== 'number' || typeof lon !== 'number') return false;
        if (!Number.isFinite(lat) || !Number.isFinite(lon)) return false;
        if (lat < -90 || lat > 90) return false;
        if (lon < -180 || lon > 180) return false;
        if (lat === 0 && lon === 0) return false;
        return true;
    }

    function _useFallback(reason) {
        console.info('[FloodLocation] Fallback:', reason);
        _status = 'fallback';
        _source = 'default';
        const cached = _restore();
        const loc = cached || { ...NAIROBI, accuracy: null, source: 'default', ts: Date.now() };
        _current = loc;
        _locationQuality = cached ? 60 : 0;
        _notify(loc, false);
        const msg = cached ? 'Using last known location' : 'Default location — allow GPS for local data';
        _showStatus(msg, '#666666', 4000);
    }

    function _acceptReading(pos) {
        const lat = pos.coords.latitude;
        const lon = pos.coords.longitude;
        const accuracy = pos.coords.accuracy;
        const altitude = pos.coords.altitude;
        const heading = pos.coords.heading;
        const speed = pos.coords.speed;

        if (!_validateCoordinates(lat, lon)) {
            _useFallback('Invalid coordinates');
            return;
        }

        if (accuracy > MAX_ACCURACY && _retryCount < RETRY_LIMIT) {
            _retryCount++;
            console.info(`[FloodLocation] Accuracy ${Math.round(accuracy)}m exceeds ${MAX_ACCURACY}m, retry ${_retryCount}/${RETRY_LIMIT}`);
            _showStatus(`GPS accuracy low (±${Math.round(accuracy)}m). Retrying...`, '#444444');
            _requestGPS();
            return;
        }

        const loc = {
            lat: lat,
            lon: lon,
            accuracy: accuracy,
            altitude: altitude,
            heading: heading,
            speed: speed,
            source: _source,
            ts: Date.now(),
            zoom: accuracy < 10 ? 17 : accuracy < 30 ? 16 : accuracy < 100 ? 15 : 13,
        };

        if (!_bestReading || (accuracy < _bestReading.accuracy)) {
            _bestReading = loc;
        }

        _current = loc;
        _status = 'granted';
        _locationQuality = _calculateQuality(loc);
        _save(loc);
        _notify(loc, true);
        const qLabel = _qualityLabel(_locationQuality);
        _showStatus(`Location detected (±${Math.round(accuracy)}m, ${qLabel})`, '#1677C8', 3000);
    }

    function _requestGPS() {
        if (!('geolocation' in navigator)) {
            _useFallback('Geolocation API not available');
            return;
        }

        _status = 'requesting';
        _source = 'gps';
        _showStatus('Detecting your location...', '#1677C8');

        navigator.geolocation.getCurrentPosition(
            function(pos) {
                _retryCount = 0;
                _acceptReading(pos);
            },
            function(err) {
                _retryCount = 0;
                const msgs = {
                    1: 'Permission denied',
                    2: 'Position unavailable',
                    3: 'Request timed out'
                };
                console.warn('[FloodLocation] GPS error:', msgs[err.code] || err.message);
                _useFallback(msgs[err.code] || 'GPS error');
            },
            {
                enableHighAccuracy: true,
                maximumAge: 0,
                timeout: GPS_TIMEOUT,
            }
        );
    }

    function _startWatch() {
        if (!('geolocation' in navigator)) return;
        if (_watchId !== null) return;

        _watchId = navigator.geolocation.watchPosition(
            function(pos) {
                _acceptReading(pos);
            },
            function(err) {
                console.warn('[FloodLocation] Watch error:', err.message);
            },
            {
                enableHighAccuracy: true,
                maximumAge: 0,
                timeout: WATCH_TIMEOUT,
            }
        );
    }

    function _stopWatch() {
        if (_watchId !== null) {
            navigator.geolocation.clearWatch(_watchId);
            _watchId = null;
        }
    }

    function _ipFallback() {
        _status = 'fallback';
        _source = 'ip';
        _showStatus('Locating via IP...', '#444444');

        fetch('https://ipapi.co/json/', { signal: AbortSignal.timeout ? AbortSignal.timeout(5000) : undefined })
            .then(r => r.ok ? r.json() : null)
            .then(data => {
                if (data && _validateCoordinates(parseFloat(data.latitude), parseFloat(data.longitude))) {
                    const loc = {
                        lat: parseFloat(data.latitude),
                        lon: parseFloat(data.longitude),
                        accuracy: 10000,
                        altitude: null,
                        heading: null,
                        speed: null,
                        source: 'ip',
                        ts: Date.now(),
                        zoom: 11,
                        city: data.city || '',
                        country: data.country_name || '',
                    };
                    _current = loc;
                    _locationQuality = 25;
                    _save(loc);
                    _notify(loc, true);
                    _showStatus(`IP location: ${loc.city || 'Unknown'} (±10km)`, '#444444', 3000);
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
            _bestReading = null;
            _retryCount = 0;
            _clearCache();

            if (strategy === 'ip') {
                _ipFallback();
                return;
            }

            _requestGPS();
            _startWatch();

            setTimeout(() => {
                if (_status === 'requesting' || _status === 'idle') {
                    _stopWatch();
                    if (_bestReading && _bestReading.accuracy <= MAX_ACCURACY) {
                        _current = _bestReading;
                        _status = 'granted';
                        _locationQuality = _calculateQuality(_bestReading);
                        _save(_current);
                        _notify(_current, true);
                    } else if (_status !== 'granted') {
                        _ipFallback();
                    }
                }
            }, GPS_TIMEOUT + 2000);
        },
        get current() { return _current; },
        get status() { return _status; },
        get default() { return NAIROBI; },
        get quality() { return _locationQuality; },
        get qualityLabel() { return _qualityLabel(_locationQuality); },
        get source() { return _source; },
        refresh: function() {
            _status = 'idle';
            _bestReading = null;
            _retryCount = 0;
            _clearCache();
            _requestGPS();
            _startWatch();
        },
        setManual: function(lat, lon, accuracy) {
            if (!_validateCoordinates(lat, lon)) {
                console.warn('[FloodLocation] Invalid manual coordinates');
                return;
            }
            _stopWatch();
            const loc = {
                lat: lat,
                lon: lon,
                accuracy: accuracy || 5,
                altitude: null,
                heading: null,
                speed: null,
                source: 'manual',
                ts: Date.now(),
                zoom: 16,
            };
            _current = loc;
            _status = 'granted';
            _source = 'manual';
            _locationQuality = _calculateQuality(loc);
            _save(loc);
            _notify(loc, true);
            _showStatus(`Location set manually (±${Math.round(loc.accuracy)}m)`, '#1677C8', 3000);
        },
        stop: function() {
            _stopWatch();
            _status = 'idle';
        },
    };
})();
