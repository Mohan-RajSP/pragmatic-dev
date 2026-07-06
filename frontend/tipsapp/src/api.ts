/**
 * API client for the tips feature.
 *
 * Centralizes all backend calls so components/hooks don't touch `fetch` or
 * endpoint URLs directly. Requests go through nginx under `/api` (see config).
 */
import { ENDPOINTS } from "./config";
import type { Tip } from "./types";

/** Shape of the GET /tip response body. */
interface TipResponse {
  tip?: Tip | null;
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

/** Send a liveness ping (fire-and-forget; triggers backend generation). */
export async function sendLiveness(): Promise<void> {
  try {
    await fetch(ENDPOINTS.liveness);
  } catch {
    // Transient; the next 30s tick retries.
  }
}

/** Open the SSE tip stream. The caller attaches listeners and closes it. */
export function openTipStream(): EventSource {
  return new EventSource(ENDPOINTS.tipStream);
}


