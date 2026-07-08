/**
 * API client for the chat feature.
 *
 * Chat is a two-step flow because SSE (EventSource) is a GET-only transport:
 *   1. POST /chat            → submit the user message (stored server-side).
 *   2. GET  /chat/stream?... → open the SSE stream that replays the reply.
 *
 * The target base URL is resolved in `config.ts` (backend origin directly in
 * local dev; `/api` via nginx when containerized).
 */
import { ENDPOINTS } from "./config";

/** Submit a user message for the given session. Throws on a non-2xx response. */
export async function submitChat(sessionId: string, message: string): Promise<void> {
  const res = await fetch(ENDPOINTS.chat, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ session_id: sessionId, message }),
  });
  if (!res.ok) {
    throw new Error(`Chat submit failed (HTTP ${res.status})`);
  }
}

/**
 * Open the SSE reply stream for a session. The caller attaches listeners for the
 * `message` / `error` / `done` events and closes the stream when finished.
 */
export function openChatStream(sessionId: string): EventSource {
  const url = `${ENDPOINTS.chatStream}?session_id=${encodeURIComponent(sessionId)}`;
  return new EventSource(url);
}

