import React from "react";

import { useTips } from "./useTips";
import type { Tip } from "./types";

function formatTime(unixSeconds: number): string {
  try {
    return new Date(unixSeconds * 1000).toLocaleTimeString([], {
      hour: "2-digit",
      minute: "2-digit",
    });
  } catch {
    return "";
  }
}

function TipCard({ tip, latest }: { tip: Tip; latest: boolean }) {
  return (
    <li
      className={`rounded-lg border p-3 shadow-sm transition-colors ${
        latest ? "border-indigo-300 bg-indigo-50" : "border-gray-200 bg-white"
      }`}
    >
      <p className="text-sm leading-relaxed text-gray-800">{tip.text}</p>
      <div className="mt-2 flex items-center justify-between">
        {latest && (
          <span className="rounded-full bg-indigo-600 px-2 py-0.5 text-[10px] font-semibold uppercase tracking-wide text-white">
            Latest
          </span>
        )}
        <time className="ml-auto text-[11px] text-gray-400">
          {formatTime(tip.created_at)}
        </time>
      </div>
    </li>
  );
}

function EmptyState({ status }: { status: string }) {
  const message =
    status === "error"
      ? "Reconnecting to tips…"
      : "Fetching your first mental-health tip…";
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-3 h-8 w-8 animate-spin rounded-full border-2 border-gray-200 border-t-indigo-500" />
      <p className="text-sm text-gray-500">{message}</p>
    </div>
  );
}

/** Shown when streaming is stopped — prompts the user to start it. */
function IdleState({ onStart }: { onStart: () => void }) {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <p className="mb-4 text-sm text-gray-500">
        The tips stream is stopped. Start it to receive fresh mental-health tips.
      </p>
      <button
        type="button"
        onClick={onStart}
        className="rounded-md bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700"
      >
        Start stream
      </button>
    </div>
  );
}

/** Shown while the stream is alive but no new tip has arrived yet. */
function WaitingCard() {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-dashed border-gray-300 bg-white/60 p-3">
      <span className="flex gap-1">
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 [animation-delay:0ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 [animation-delay:150ms]" />
        <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 [animation-delay:300ms]" />
      </span>
      <span className="text-xs italic text-gray-500">Waiting for the next tip…</span>
    </li>
  );
}

export function TipsPanel(): React.ReactElement {
  const { tips, status, waiting, streaming, initializing, start, stop } = useTips();
  const hasTips = tips.length > 0;

  return (
    <div className="flex h-full flex-col bg-gray-50">
      <header className="flex items-center gap-2 border-b border-gray-200 bg-white px-4 py-3">
        <span
          className={`h-2 w-2 rounded-full ${
            status === "open"
              ? "bg-green-500"
              : status === "error"
                ? "bg-red-500"
                : status === "connecting"
                  ? "bg-amber-400"
                  : "bg-gray-300"
          }`}
          title={`Stream: ${status}`}
        />
        <h2 className="text-sm font-semibold text-gray-700">Mental-health tips</h2>
        <button
          type="button"
          onClick={streaming ? stop : start}
          className={`ml-auto rounded-md px-3 py-1 text-xs font-semibold text-white shadow-sm transition-colors ${
            streaming
              ? "bg-red-500 hover:bg-red-600"
              : "bg-indigo-600 hover:bg-indigo-700"
          }`}
          title={streaming ? "Stop the tips stream" : "Start the tips stream"}
        >
          {streaming ? "Stop stream" : "Start stream"}
        </button>
      </header>

      {hasTips ? (
        // Tips exist → always show them, whether streaming or stopped. The
        // "waiting" placeholder only appears while actively streaming.
        <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {streaming && waiting && <WaitingCard />}
          {tips.map((tip, i) => (
            <TipCard key={tip.id} tip={tip} latest={i === 0} />
          ))}
        </ul>
      ) : initializing ? (
        // First load: history request still in flight.
        <EmptyState status={status} />
      ) : streaming ? (
        // Streaming with an empty cache → waiting for the first generated tip.
        waiting ? (
          <ul className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
            <WaitingCard />
          </ul>
        ) : (
          <EmptyState status={status} />
        )
      ) : (
        // Stopped and no history yet → prompt to start.
        <IdleState onStart={start} />
      )}
    </div>
  );
}

