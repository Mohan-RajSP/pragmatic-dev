import React, { useEffect, useRef, useState } from "react";

import { useChat } from "./useChat";
import type { ChatMessage } from "./types";

/** A single chat bubble — user (right, indigo) vs assistant (left, white). */
function MessageBubble({ message, streaming }: { message: ChatMessage; streaming: boolean }) {
  const isUser = message.role === "user";
  const showCaret = !isUser && streaming && message.content === "";

  return (
    <div className={`flex ${isUser ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[80%] whitespace-pre-wrap rounded-2xl px-4 py-2 text-sm leading-relaxed shadow-sm ${
          isUser
            ? "rounded-br-sm bg-indigo-600 text-white"
            : message.error
              ? "rounded-bl-sm border border-red-200 bg-red-50 text-red-700"
              : "rounded-bl-sm border border-gray-200 bg-white text-gray-800"
        }`}
      >
        {showCaret ? <TypingDots /> : message.content}
      </div>
    </div>
  );
}

/** Animated "assistant is typing" indicator. */
function TypingDots() {
  return (
    <span className="inline-flex gap-1 py-1">
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 [animation-delay:0ms]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 [animation-delay:150ms]" />
      <span className="h-1.5 w-1.5 animate-pulse rounded-full bg-indigo-400 [animation-delay:300ms]" />
    </span>
  );
}

/** Shown before any messages exist. */
function EmptyState() {
  return (
    <div className="flex h-full flex-col items-center justify-center px-6 text-center">
      <div className="mb-3 flex h-12 w-12 items-center justify-center rounded-full bg-indigo-100 text-2xl">
        💬
      </div>
      <h3 className="text-base font-semibold text-gray-700">How are you feeling today?</h3>
      <p className="mt-1 max-w-sm text-sm text-gray-500">
        Ask anything about well-being, stress, focus, or mindfulness. This is a
        supportive space — not a substitute for professional help.
      </p>
    </div>
  );
}

export function ChatPanel(): React.ReactElement {
  const { messages, status, error, busy, sendMessage } = useChat();
  const [draft, setDraft] = useState("");
  const scrollRef = useRef<HTMLDivElement | null>(null);
  const textareaRef = useRef<HTMLTextAreaElement | null>(null);

  // Auto-scroll the conversation container (NOT the window) to the newest token.
  useEffect(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages]);

  const submit = () => {
    const text = draft.trim();
    if (!text || busy) return;
    sendMessage(text);
    setDraft("");
  };

  const onKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    // Enter sends; Shift+Enter inserts a newline.
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      submit();
    }
  };

  const hasMessages = messages.length > 0;

  return (
    <div className="flex h-full flex-col bg-gray-50">
      <header className="flex items-center gap-2 border-b border-gray-200 bg-white px-4 py-3">
        <span
          className={`h-2 w-2 rounded-full ${
            status === "streaming"
              ? "bg-green-500"
              : status === "sending"
                ? "bg-amber-400"
                : status === "error"
                  ? "bg-red-500"
                  : "bg-gray-300"
          }`}
          title={`Status: ${status}`}
        />
        <h2 className="text-sm font-semibold text-gray-700">Chat</h2>
      </header>

      {/* Conversation */}
      <div ref={scrollRef} className="min-h-0 flex-1 overflow-y-auto">
        {hasMessages ? (
          <div className="space-y-3 p-4">
            {messages.map((m) => (
              <MessageBubble key={m.id} message={m} streaming={status === "streaming"} />
            ))}
          </div>
        ) : (
          <EmptyState />
        )}
      </div>

      {error && (
        <div className="border-t border-red-100 bg-red-50 px-4 py-2 text-xs text-red-600">
          {error}
        </div>
      )}

      {/* Composer */}
      <div className="border-t border-gray-200 bg-white p-3">
        <div className="flex items-end gap-2">
          <textarea
            ref={textareaRef}
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={onKeyDown}
            rows={1}
            placeholder="Type your message…  (Enter to send, Shift+Enter for a new line)"
            className="max-h-40 flex-1 resize-none rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-800 shadow-sm outline-none focus:border-indigo-400 focus:ring-2 focus:ring-indigo-100"
          />
          <button
            type="button"
            onClick={submit}
            disabled={busy || draft.trim() === ""}
            className="rounded-lg bg-indigo-600 px-4 py-2 text-sm font-semibold text-white shadow-sm transition-colors hover:bg-indigo-700 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "…" : "Send"}
          </button>
        </div>
      </div>
    </div>
  );
}



