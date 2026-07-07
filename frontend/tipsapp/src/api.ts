/**
 * API client for the tips feature.
 *
 * Centralizes all backend calls so components/hooks don't touch `fetch` or
 * endpoint URLs directly. The target base URL is resolved in `config.ts`
 * (backend origin directly in local dev; `/api` via nginx when containerized).
 */
import { ENDPOINTS } from "./config";
import type { Tip } from "./types";

/** Shape of the GET /tip response body. */
interface TipResponse {
  tip?: Tip | null;
}

/** Shape of the GET /tip/history response body. */
interface TipListResponse {
  tips?: Tip[];
}

/** Fetch the latest tip once. Returns `null` if none exist or on error. */
export async function fetchLatestTip(): Promise<Tip | null> {
  try {
    const res = await fetch(ENDPOINTS.latestTip);
    if (!res.ok) return null;
    const body = await res.json();
    const data = body as TipResponse;
    return data.tip ?? null;
  } catch {
    // Ignore — the SSE stream will deliver a tip when one is available.
    return null;
  }
}

/**
 * Fetch all cached tips (newest first) to hydrate the panel on load/reconnect.
 * Returns an empty array if none exist or on error.
 */
export async function fetchRecentTips(): Promise<Tip[]> {
  try {
    const res = await fetch(ENDPOINTS.tipHistory);
    if (!res.ok) return [];
    const body = await res.json();
    const data = body as TipListResponse;
    return data.tips ?? [];
  } catch {
    // Ignore — the SSE stream will keep the panel updated.
    return [];
  }
}

/** Send a liveness ping (fire-and-forget; triggers backend generation). */
export async function sendLiveness(): Promise<void> {
  try {
    // POST because the ping mutates server state (sets the Redis trigger and
    // may dispatch a cold-start generation task) — not a safe/idempotent GET.
    await fetch(ENDPOINTS.liveness, { method: "POST" });
  } catch {
    // Transient; the next 30s tick retries.
  }
}

/** Open the SSE tip stream. The caller attaches listeners and closes it. */
export function openTipStream(): EventSource {
  return new EventSource(ENDPOINTS.tipStream);
}


