// Dashboard page JS
// Initialize Leaflet map and fetch live flood data
import { API_BASE_URL, getAuthHeader } from './utils.js';

document.addEventListener('DOMContentLoaded', () => {
    const map = L.map('map').setView([0, 0], 2);
    L.tileLayer('https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png', {
        attribution: '© OpenStreetMap contributors'
    }).addTo(map);
    // Fetch and display flood data here
});