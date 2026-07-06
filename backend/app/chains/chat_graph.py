"""LangGraph chat workflow.

For now the workflow has a single node ("chat") that runs an LCEL pipeline
(prompt -> LLM). The prompt, model, and invocation are kept as distinct steps
per the project conventions. Token streaming is obtained by consuming
`graph.astream_events(...)` in the chat service.

Conversation memory:
The graph is compiled with an in-process `MemorySaver` checkpointer, keyed by
`thread_id` (== session_id). This gives multi-turn context *within* a running
session — each request only sends the new user message and the checkpointer
restores/append the prior history for that thread.

Trade-offs of `MemorySaver` (acceptable for the current phase):
  * Volatile — state lives in RAM and is lost on process restart / page refresh
    (by design; matches the "history in frontend state" decision).
  * Per-process — not shared across backend replicas. Fine while we run a
    single backend and have no auth/session persistence yet. When we add auth +
    the DB/RAG phase, swap this for a persistent, shared checkpointer
    (e.g. Redis/Postgres saver) — no call-site changes needed.
"""

from __future__ import annotations

from functools import lru_cache

from langchain_core.messages import SystemMessage
from langchain_core.prompts import ChatPromptTemplate, MessagesPlaceholder
from langchain_core.runnables import Runnable
from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, START, MessagesState, StateGraph
from langgraph.graph.state import CompiledStateGraph

from app.llm.factory import get_llm_strategy

_SYSTEM_PROMPT = (
    "You are a supportive, empathetic assistant for a mental-health and "
    "well-being learning application. Provide thoughtful, safe, and encouraging "
    "responses. You are not a substitute for professional help; gently suggest "
    "seeking a professional when a situation seems serious."
)


def _build_chat_chain() -> Runnable:
    """LCEL pipeline: prompt step | LLM step."""
    # Step 1 — prompt
    prompt = ChatPromptTemplate.from_messages(
        [
            SystemMessage(content=_SYSTEM_PROMPT),
            MessagesPlaceholder(variable_name="messages"),
        ]
    )
    # Step 2 — model (streaming enabled for token-by-token SSE)
    model = get_llm_strategy().build_model(streaming=True)
    # Step 3 — compose
    return prompt | model


@lru_cache
def build_chat_graph() -> CompiledStateGraph:
    """Compile and cache the single-node chat graph.

    Cached so the compiled graph — and its `MemorySaver` — is a process-wide
    singleton, letting memory persist across requests for the same session.
    """
    chain = _build_chat_chain()

    async def call_model(state: MessagesState) -> dict:
        # Step 3 — invoke (async so astream_events can surface token stream).
        # `state["messages"]` already includes prior turns restored by the
        # checkpointer for this thread_id; the reducer appends the new ones.
        response = await chain.ainvoke({"messages": state["messages"]})
        return {"messages": [response]}

    builder = StateGraph(MessagesState)
    builder.add_node("chat", call_model)
    builder.add_edge(START, "chat")
    builder.add_edge("chat", END)
    # In-process memory keyed by thread_id (== session_id). Volatile by design.
    return builder.compile(checkpointer=MemorySaver())



