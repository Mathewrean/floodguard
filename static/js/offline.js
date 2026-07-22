(function() {
    if ('serviceWorker' in navigator) {
        navigator.serviceWorker.register('/service-worker.js').then(() => {
            console.info('[SW] Registered');
            if (document.body.dataset.authenticated === 'true') {
                requestPushPermission();
            }
        }).catch(e => console.warn('[SW] Registration failed:', e));
    }

    let offlineBanner = null;

    function showOfflineBanner() {
        if (offlineBanner) return;
        offlineBanner = document.createElement('div');
        offlineBanner.id = 'fg-offline-banner';
        offlineBanner.innerHTML = '<span>⚡ You are offline</span><span style="font-size:12px;opacity:0.8">Showing last cached data</span>';
        offlineBanner.style.cssText = [
            'position:fixed','top:64px','left:0','right:0',
            'background:#DC2626','color:#fff',
            'padding:8px 16px','text-align:center',
            'z-index:9998','display:flex',
            'justify-content:center','gap:16px',
            'align-items:center','font-size:14px',
            'font-weight:600',
        ].join(';');
        document.body.appendChild(offlineBanner);
        document.querySelectorAll('[data-live]').forEach(el => {
            el.dataset.stale = 'true';
            const badge = document.createElement('span');
            badge.className = 'stale-badge';
            badge.textContent = 'Cached';
            el.appendChild(badge);
        });
    }

    function hideOfflineBanner() {
        if (!offlineBanner) return;
        offlineBanner.remove();
        offlineBanner = null;
        document.querySelectorAll('.stale-badge').forEach(el => el.remove());
        if (window.refreshAllData) window.refreshAllData();
    }

    window.addEventListener('offline', showOfflineBanner);
    window.addEventListener('online', hideOfflineBanner);
    if (!navigator.onLine) showOfflineBanner();

    window.offlineFetch = async function(url) {
        if (!navigator.onLine) {
            const cache = await caches.open('fg-api-cache').catch(() => null);
            if (cache) {
                const cached = await cache.match(url).catch(() => null);
                if (cached) return cached.json();
            }
            throw new Error('Offline and no cache available');
        }
        const res = await fetch(url);
        if (!res.ok) throw new Error(`HTTP ${res.status}`);
        return res.json();
    };

    async function requestPushPermission() {
        if (!('PushManager' in window)) return;
        const permission = await Notification.requestPermission();
        if (permission !== 'granted') return;
        const sub = await navigator.serviceWorker.ready.then(reg => 
            reg.pushManager.subscribe({ userVisibleOnly: true })
        ).catch(() => null);
        if (sub) {
            await fetch('/api/v1/push/subscribe/', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json', 'X-CSRFToken': getCookie('csrftoken') },
                body: JSON.stringify(sub.toJSON()),
            }).catch(() => {});
        }
    }

    function getCookie(name) {
        const val = `; ${document.cookie}`;
        const parts = val.split(`; ${name}=`);
        if (parts.length === 2) return parts.pop().split(';').shift();
    }
})();