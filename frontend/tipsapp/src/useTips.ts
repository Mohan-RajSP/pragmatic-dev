import { useCallback, useEffect, useRef, useState } from "react";

import { fetchRecentTips, openTipStream, sendLiveness } from "./api";
import { LIVENESS_INTERVAL_MS, MAX_TIPS } from "./config";
import type { Tip } from "./types";

type Status = "idle" | "connecting" | "open" | "error";

interface UseTipsResult {
  tips: Tip[];
  status: Status;
  error: string | null;
  waiting: boolean;
  streaming: boolean;
  initializing: boolean;
  start: () => void;
  stop: () => void;
}

/**
 * Manages the tips lifecycle for the panel.
 *
 * On mount it ALWAYS loads the existing tip history once (so the panel shows
 * cached tips by default, before any streaming). Streaming itself is *manually*
 * controlled via `start()` / `stop()` to avoid constant SSE + liveness usage.
 *
 * When started it:
 *  1. Re-fetches history (to catch tips generated while it was stopped).
 *  2. Opens an SSE stream; handles two named events:
 *       - "tip"       → prepend the new tip (deduped by id, capped).
 *       - "heartbeat" → connection alive but no new tip → "waiting" state.
 *  3. Pings liveness immediately, then every 30s (triggers fresh generation /
 *     cold-start on the backend).
 *
 * When stopped it closes the `EventSource` and clears the liveness interval, but
 * DELIBERATELY preserves the accumulated tips (and their dedup set) so the
 * history stays visible after stopping.
 */
export function useTips(): UseTipsResult {
  const [tips, setTips] = useState<Tip[]>([]);
  const [status, setStatus] = useState<Status>("idle");
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);
  const [streaming, setStreaming] = useState(false);
  const [initializing, setInitializing] = useState(true);
  const seenIds = useRef<Set<string>>(new Set());

  const start = useCallback(() => setStreaming(true), []);
  const stop = useCallback(() => setStreaming(false), []);

  // Stable inserter: dedup by id, keep newest-first, cap at MAX_TIPS.
  const addTip = useCallback((tip: Tip) => {
    if (!tip || seenIds.current.has(tip.id)) return;
    seenIds.current.add(tip.id);
    setTips((prev) => [tip, ...prev].slice(0, MAX_TIPS));
  }, []);

  // On mount: fetch existing history so cached tips render immediately, even
  // before the user starts the stream (and they persist after stopping).
  useEffect(() => {
    let cancelled = false;
    fetchRecentTips()
      .then((history) => {
        if (cancelled) return;
        // History is newest-first; addTip prepends, so apply oldest→newest.
        for (const tip of [...history].reverse()) addTip(tip);
      })
      .finally(() => {
        if (!cancelled) setInitializing(false);
      });
    return () => {
      cancelled = true;
    };
  }, [addTip]);

  useEffect(() => {
    if (!streaming) return;

    let cancelled = false;
    setStatus("connecting");
    setError(null);

    // 1. Refresh history on (re)start to pick up tips generated while stopped.
    fetchRecentTips().then((history) => {
      if (cancelled) return;
      for (const tip of [...history].reverse()) addTip(tip);
    });

    // 2. SSE stream (browser auto-reconnects). onopen/onerror are connection
    //    level; the "tip"/"heartbeat" data events use addEventListener.
    const es = openTipStream();

    es.onopen = () => {
      if (!cancelled) {
        setStatus("open");
        setError(null);
      }
    };

    es.onerror = () => {
      if (!cancelled) {
        setStatus("error");
        setError("Connection to the tips stream was lost. Reconnecting…");
      }
    };

    es.addEventListener("tip", (e) => {
      if (cancelled) return;
      try {
        addTip(JSON.parse((e as MessageEvent).data) as Tip);
        setWaiting(false);
      } catch {
        /* ignore malformed frame */
      }
    });

    es.addEventListener("heartbeat", () => {
      // Alive, but no new tip since the last one — show the waiting state.
      if (!cancelled) setWaiting(true);
    });

    // Server-sent error (e.g. Redis unavailable): the backend closes the stream
    // after this. Show a meaningful message; EventSource will auto-reconnect.
    es.addEventListener("error", (e) => {
      if (cancelled) return;
      const data = (e as MessageEvent).data;
      if (!data) return; // connection-level error → handled by es.onerror
      try {
        const { detail } = JSON.parse(data) as { detail?: string };
        setStatus("error");
        setError(detail ?? "The tips service is temporarily unavailable. Reconnecting…");
        setWaiting(false);
      } catch {
        /* ignore malformed frame */
      }
    });

    // 3. Liveness ping now + every 30s.
    sendLiveness();
    const interval = window.setInterval(sendLiveness, LIVENESS_INTERVAL_MS);

    return () => {
      cancelled = true;
      es.close();
      window.clearInterval(interval);
      setStatus("idle");
      setWaiting(false);
      // NOTE: `tips` and `seenIds` are intentionally NOT cleared here so the
      // accumulated history remains visible after the stream is stopped.
    };
  }, [streaming, addTip]);

  return { tips, status, error, waiting, streaming, initializing, start, stop };
}


