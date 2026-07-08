/** A chat participant. */
export type ChatRole = "user" | "assistant";

/** A single chat message rendered in the conversation. */
export interface ChatMessage {
  id: string;
  role: ChatRole;
  content: string;
  /** True when this (assistant) message represents an error notice. */
  error?: boolean;
}

/** Stream lifecycle status for the current turn. */
export type ChatStatus = "idle" | "sending" | "streaming" | "error";

