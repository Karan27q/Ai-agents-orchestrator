// Single source of truth for the API base URL.
//
// Production: the SPA is served by FastAPI, so a same-origin relative path
// keeps the Content-Security-Policy tight (`connect-src 'self'`).
// Development: Vite proxies /api to http://localhost:8000 (see vite.config.js),
// or set VITE_API_URL to point at a different backend.
export const API_URL = import.meta.env.VITE_API_URL || '/api/v1';
