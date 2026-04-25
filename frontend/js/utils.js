// Utility functions for API calls and config
export const API_BASE_URL = '/api';
export function getAuthHeader() {
    const token = localStorage.getItem('jwt');
    return token ? { 'Authorization': `Bearer ${token}` } : {};
}