import { useCallback, useEffect, useRef, useState } from "react";

import { openChatStream, submitChat } from "./api";
import type { ChatMessage, ChatStatus } from "./types";

interface UseChatResult {
  messages: ChatMessage[];
  status: ChatStatus;
  error: string | null;
  /** True while a reply is being submitted or streamed (input should lock). */
  busy: boolean;
  sendMessage: (text: string) => void;
}

/** Small unique-id helper (crypto.randomUUID is available in secure contexts). */
function makeId(): string {
  try {
    return crypto.randomUUID();
  } catch {
    return `${Date.now()}-${Math.random().toString(16).slice(2)}`;
  }
}

/**
 * Manages the chat conversation and streaming lifecycle.
 *
 * Flow per turn:
 *  1. Append the user's message + an empty assistant placeholder.
 *  2. POST /chat to submit the message (stored server-side, keyed by session).
 *  3. Open GET /chat/stream; append streamed tokens to the placeholder as the
 *     `message` events arrive. Close on `done` (or on `error`).
 *
 * `session_id` is stable for the component's lifetime, so the backend's
 * per-session memory keeps multi-turn context. History lives only in this state
 * (lost on refresh) — matching the current-phase design.
 */
export function useChat(): UseChatResult {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [status, setStatus] = useState<ChatStatus>("idle");
  const [error, setError] = useState<string | null>(null);

  // Stable session id for the whole mount (lazy-initialized once).
  const sessionIdRef = useRef<string>("");
  if (!sessionIdRef.current) sessionIdRef.current = makeId();

  // Track the active stream so we can close it on unmount / new turn.
  const esRef = useRef<EventSource | null>(null);

  const busy = status === "sending" || status === "streaming";

  // Append text to a specific (assistant) message by id.
  const appendToMessage = useCallback((id: string, chunk: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: m.content + chunk } : m)),
    );
  }, []);

  // Replace a message's content (used to surface an error in-place).
  const setMessageError = useCallback((id: string, text: string) => {
    setMessages((prev) =>
      prev.map((m) => (m.id === id ? { ...m, content: text, error: true } : m)),
    );
  }, []);

  const sendMessage = useCallback(
    (text: string) => {
      const trimmed = text.trim();
      if (!trimmed || busy) return;

      // Close any lingering stream from a previous turn defensively.
      esRef.current?.close();
      esRef.current = null;

      setError(null);
      const assistantId = makeId();
      setMessages((prev) => [
        ...prev,
        { id: makeId(), role: "user", content: trimmed },
        { id: assistantId, role: "assistant", content: "" },
      ]);
      setStatus("sending");

      void (async () => {
        try {
          // 1. Submit the message so the stream has something to claim.
          await submitChat(sessionIdRef.current, trimmed);
        } catch {
          setStatus("error");
          setError("Couldn't reach the chat service. Please try again.");
          setMessageError(assistantId, "⚠️ Failed to send your message.");
          return;
        }

        // 2. Open the SSE reply stream.
        setStatus("streaming");
        const es = openChatStream(sessionIdRef.current);
        esRef.current = es;

        es.addEventListener("message", (e) => {
          appendToMessage(assistantId, (e as MessageEvent).data as string);
        });

        // Server-sent, application-level error (has data).
        es.addEventListener("error", (e) => {
          const data = (e as MessageEvent).data;
          if (!data) return; // connection-level error → handled by onerror
          setStatus("error");
          setError(typeof data === "string" ? data : "The chat service reported an error.");
          setMessageError(assistantId, "⚠️ The assistant ran into an error.");
          es.close();
          esRef.current = null;
        });

        // Normal completion.
        es.addEventListener("done", () => {
          es.close();
          esRef.current = null;
          setStatus("idle");
          // If nothing streamed, show a gentle fallback.
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.content === ""
                ? { ...m, content: "(No response was generated.)", error: true }
                : m,
            ),
          );
        });

        // Connection-level failure (no data). Don't auto-reconnect — the pending
        // message was already claimed server-side, so a reconnect would find
        // nothing. Close and surface an error.
        es.onerror = () => {
          if (esRef.current !== es) return; // already closed cleanly
          setStatus("error");
          setError("The connection to the chat stream was lost.");
          setMessages((prev) =>
            prev.map((m) =>
              m.id === assistantId && m.content === ""
                ? { ...m, content: "⚠️ Connection lost before a reply arrived.", error: true }
                : m,
            ),
          );
          es.close();
          esRef.current = null;
        };
      })();
    },
    [busy, appendToMessage, setMessageError],
  );

  // Close the stream if the component unmounts mid-reply.
  useEffect(() => {
    return () => {
      esRef.current?.close();
      esRef.current = null;
    };
  }, []);

  return { messages, status, error, busy, sendMessage };
}


