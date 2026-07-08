/**
 * API configuration.
 *
 * Local dev (no nginx): the queryapp talks to the FastAPI backend **directly**
 * at its origin (default below). The backend serves routes at the root (`/chat`,
 * `/chat/stream`) — there is no `/api` prefix on the backend itself.
 *
 * Containerized / prod (behind nginx): nginx exposes the backend under `/api`
 * and strips it (`/api/chat` -> backend `/chat`). In that setup, override the
 * base at runtime by setting `window.__QUERY_API_BASE__ = "/api"` (e.g. injected
 * by the baseapp shell per environment), so the same bundle works everywhere.
 */
export const API_BASE: string =
  (window as unknown as { __QUERY_API_BASE__?: string }).__QUERY_API_BASE__ ??
  "http://localhost:8000";

export const ENDPOINTS = {
  chat: `${API_BASE}/chat`,
  chatStream: `${API_BASE}/chat/stream`,
} as const;

/** Terminal SSE marker sent by the backend when a reply is complete. */
export const DONE_MARKER = "[DONE]";

