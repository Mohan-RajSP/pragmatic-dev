import { useEffect, useRef, useState } from "react";

import { fetchLatestTip, openTipStream, sendLiveness } from "./api";
import { LIVENESS_INTERVAL_MS, MAX_TIPS } from "./config";
import type { Tip } from "./types";

type Status = "connecting" | "open" | "error";

interface UseTipsResult {
  tips: Tip[];
  status: Status;
  error: string | null;
  waiting: boolean;
}

/**
 * Manages the tips lifecycle for the panel:
 *  1. Fetch the latest tip once (may be null on a cold cache → loading state).
 *  2. Open an SSE stream; handle two named events:
 *       - "tip"       → prepend the new tip (deduped by id, capped).
 *       - "heartbeat" → connection alive but no new tip → "waiting" state.
 *  3. Ping liveness immediately, then every 30s (triggers fresh generation /
 *     cold-start on the backend).
 *
 * The frontend never polls `/tip` — the stream delivers updates. `EventSource`
 * auto-reconnects on drop, so no manual retry logic is needed.
 */
export function useTips(): UseTipsResult {
  const [tips, setTips] = useState<Tip[]>([]);
  const [status, setStatus] = useState<Status>("connecting");
  const [error, setError] = useState<string | null>(null);
  const [waiting, setWaiting] = useState(false);
  const seenIds = useRef<Set<string>>(new Set());

  useEffect(() => {
    let cancelled = false;

    const addTip = (tip: Tip) => {
      if (!tip || seenIds.current.has(tip.id)) return;
      seenIds.current.add(tip.id);
      setTips((prev) => [tip, ...prev].slice(0, MAX_TIPS));
    };

    // 1. Initial value (best-effort; empty cache is fine).
    fetchLatestTip().then((tip) => {
      if (!cancelled && tip) {
        addTip(tip);
      }
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

    // 3. Liveness ping now + every 30s.
    sendLiveness();
    const interval = window.setInterval(sendLiveness, LIVENESS_INTERVAL_MS);

    return () => {
      cancelled = true;
      es.close();
      window.clearInterval(interval);
    };
  }, []);

  return { tips, status, error, waiting };
}


