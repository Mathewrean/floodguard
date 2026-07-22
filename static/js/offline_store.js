(function() {
    const DB_NAME = 'floodguard_offline';
    const DB_VERSION = 1;
    let db = null;

    function openDB() {
        return new Promise((resolve, reject) => {
            if (db) { resolve(db); return; }
            const req = indexedDB.open(DB_NAME, DB_VERSION);
            req.onupgradeneeded = e => {
                const d = e.target.result;
                if (!d.objectStoreNames.contains('pending_reports')) {
                    d.createObjectStore('pending_reports', { keyPath: 'id', autoIncrement: true });
                }
                if (!d.objectStoreNames.contains('cached_zones')) {
                    d.createObjectStore('cached_zones', { keyPath: 'id' });
                }
            };
            req.onsuccess = e => { db = e.target.result; resolve(db); };
            req.onerror = () => reject(req.error);
        });
    }

    window.OfflineStore = {
        savePendingReport: async function(reportData) {
            const d = await openDB();
            return new Promise((resolve, reject) => {
                const tx = d.transaction('pending_reports', 'readwrite');
                const store = tx.objectStore('pending_reports');
                const req = store.add({ ...reportData, created_offline: new Date().toISOString(), synced: false });
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
        },
        getPendingReports: async function() {
            const d = await openDB();
            return new Promise((resolve, reject) => {
                const tx = d.transaction('pending_reports', 'readonly');
                const store = tx.objectStore('pending_reports');
                const req = store.getAll();
                req.onsuccess = () => resolve(req.result.filter(r => !r.synced));
                req.onerror = () => reject(req.error);
            });
        },
        markSynced: async function(id) {
            const d = await openDB();
            return new Promise((resolve, reject) => {
                const tx = d.transaction('pending_reports', 'readwrite');
                const store = tx.objectStore('pending_reports');
                const getReq = store.get(id);
                getReq.onsuccess = () => {
                    const item = getReq.result;
                    item.synced = true;
                    store.put(item).onsuccess = resolve;
                };
                getReq.onerror = () => reject(getReq.error);
            });
        },
        cacheZones: async function(zones) {
            const d = await openDB();
            const tx = d.transaction('cached_zones', 'readwrite');
            const store = tx.objectStore('cached_zones');
            store.clear();
            zones.forEach(z => store.put(z));
        },
        getCachedZones: async function() {
            const d = await openDB();
            return new Promise((resolve, reject) => {
                const tx = d.transaction('cached_zones', 'readonly');
                const req = tx.objectStore('cached_zones').getAll();
                req.onsuccess = () => resolve(req.result);
                req.onerror = () => reject(req.error);
            });
        },
        syncPendingReports: async function() {
            const pending = await this.getPendingReports();
            if (pending.length === 0) return;
            console.info(`[Offline] Syncing ${pending.length} reports`);
            const csrf = document.cookie.match(/csrftoken=([^;]+)/);
            for (const report of pending) {
                try {
                    const fd = new FormData();
                    Object.entries(report).forEach(([k, v]) => {
                        if (!['id','created_offline','synced'].includes(k)) {
                            fd.append(k, v);
                        }
                    });
                    const res = await fetch('/api/v1/reports/', {
                        method: 'POST',
                        headers: csrf ? {'X-CSRFToken': csrf[1]} : {},
                        body: fd,
                    });
                    if (res.ok) {
                        await this.markSynced(report.id);
                        console.info(`[Offline] Synced report ${report.id}`);
                    }
                } catch(e) {
                    console.warn(`[Offline] Sync failed for ${report.id}:`, e);
                }
            }
        },
    };

    window.addEventListener('online', () => {
        OfflineStore.syncPendingReports();
    });
})();