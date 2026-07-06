/**
 * API configuration.
 *
 * All requests go through nginx under `/api`, so relative paths work in the
 * containerized setup. Override at build time via the global if needed.
 */
export const API_BASE: string =
  (window as unknown as { __TIPS_API_BASE__?: string }).__TIPS_API_BASE__ ?? "/api";

export const ENDPOINTS = {
  latestTip: `${API_BASE}/tip`,
  tipStream: `${API_BASE}/tip/stream`,
  liveness: `${API_BASE}/tip/liveness`,
} as const;

/** How often to send the liveness ping (ms). */
export const LIVENESS_INTERVAL_MS = 30_000;

/** Max tips retained in the panel (mirrors the backend cache cap). */
export const MAX_TIPS = 10;

