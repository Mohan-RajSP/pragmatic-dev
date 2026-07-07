/**
 * API configuration.
 *
 * Local dev (no nginx): the tipsapp talks to the FastAPI backend **directly**
 * at its origin (default below). The backend serves routes at the root (`/tip`,
 * `/tip/stream`, …) — there is no `/api` prefix on the backend itself.
 *
 * Containerized / prod (behind nginx): nginx exposes the backend under `/api`
 * and strips it (`/api/tip` -> backend `/tip`). In that setup, override the base
 * at runtime by setting `window.__TIPS_API_BASE__ = "/api"` (e.g. injected by the
 * baseapp shell per environment), so the same bundle works everywhere.
 */
export const API_BASE: string =
  (window as unknown as { __TIPS_API_BASE__?: string }).__TIPS_API_BASE__ ??
  "http://localhost:8000";

export const ENDPOINTS = {
  latestTip: `${API_BASE}/tip`,
  tipHistory: `${API_BASE}/tip/history`,
  tipStream: `${API_BASE}/tip/stream`,
  liveness: `${API_BASE}/tip/liveness`,
} as const;

/** How often to send the liveness ping (ms). */
export const LIVENESS_INTERVAL_MS = 30_000;

/** Max tips retained in the panel (mirrors the backend cache cap). */
export const MAX_TIPS = 10;

