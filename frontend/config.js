/**
 * Frontend Configuration
 * 
 * When served from FastAPI backend (/app), use empty string for same-origin requests.
 * For separate frontend server, use full URL.
 */

const CONFIG = {
    // ============================================================
    // API BASE URL
    // ============================================================

    // When served from FastAPI backend (recommended for mobile testing)
    // For localhost: "http://127.0.0.1:8000"
    // For mobile testing on same network, use your PC's IP:
    API_BASE_URL: "http://127.0.0.1:8000",

    // For local dev with separate frontend server:
    // API_BASE_URL: "http://127.0.0.1:8000",

    // For ngrok with separate frontend (not needed if using /app route):
    // API_BASE_URL: "https://YOUR-NGROK-URL.ngrok-free.app",

    // ============================================================
    // Other settings
    // ============================================================
    THREAD_STORAGE_KEY: "credence_thread_id",
};

// Make config globally available
window.CONFIG = CONFIG;
