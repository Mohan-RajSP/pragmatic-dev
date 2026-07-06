# Pragmatic-dev — Implementation Plan

> This document captures the **finalized architecture decisions** agreed during planning.
> It refines and supersedes ambiguous points in `copilot-instructions.md` where the two differ
> (e.g. chat now uses direct `astream` instead of Celery). Keep this file updated as decisions evolve.

**Domain:** `pragmatic-dev.in` · **Purpose:** learning & development · **Date finalized:** 2026-07-05

---

## 1. High-Level Architecture

Monolithic-but-modular application, designed to split into microservices later.

- **Backend:** FastAPI (Python **3.12**, packaged with **uv**)
- **Worker:** Celery + Celery Beat (Redis broker) — used for **tips generation only** for now
- **Frontend:** React + **TypeScript**, micro-frontends via **single-spa** (Webpack, **SystemJS import-maps**)
- **Cache/Broker:** Redis
- **Reverse proxy:** nginx
- **Orchestration:** Docker Compose now → Kubernetes later
- **Deployment (future):** AWS ECS + ECR

---

## 2. Confirmed Decisions (Q&A outcomes)

| Topic | Decision |
|---|---|
| Frontend roles | `baseapp` = single-spa root-config/shell (served on a port); `tipsapp` = tips side panel (30%); `queryapp` = chat (70%) |
| Parcel loading | `baseapp` uses **single-spa-layout** engine and mounts `tipsapp`/`queryapp` as **single-spa parcels** |
| MFE module loading | **SystemJS import-maps** for now (migrate to Module Federation later) |
| Frontend language | **TypeScript** |
| Bundler | **Webpack** (via `create-single-spa`) |
| Styling | **Tailwind CSS** with **per-MFE Shadow DOM isolation** — each parcel renders into its own shadow root; compiled Tailwind CSS injected *inside* the shadow root (constructable stylesheet / `<style>`); no `preflight` duplication or prefix hacks needed |
| CSS isolation | **Shadow DOM per MFE**. Notes: (1) inject Tailwind styles inside each shadow root via `single-spa-react` `domElementGetter`; (2) requires **React 17+** for event delegation inside shadow roots; (3) **portals** (modals/menus) must target a container *inside* the shadow root or they lose styles; (4) **CSS custom properties pierce the boundary** → share design tokens via CSS variables; (5) load `@font-face` at document level |
| Python packaging | **uv**, Python **3.12** |
| LLM | OpenAI **GPT-4**, API key from `.env`; **strategy pattern** chooses model via env var |
| LangChain | **LCEL** pipeline — prompt / LLM call / invoke as separate steps |
| Tips SSE mechanism | Celery writes tip to a specific Redis key; API SSE handler reads that key and streams |
| Liveness endpoint | **`/tip/liveness`** (corrected from `/sse/liveness`) |
| Chat transport | **Direct `astream`** in FastAPI (NO Celery for chat now) |
| Chat endpoints | `POST /chat` (submit) + `GET /chat/stream` (SSE reply) |
| Future chat scaling | Introduce **Redis Streams / Kafka** when RAG pipeline is added |
| Reverse proxy | **nginx** now: `/` → baseapp, `/api` → backend (SSE buffering disabled) |
| Only exposed frontend | `baseapp` (its own container/port); other MFEs consumed by the shell |
| Frontend serving | **Express** (`server.js`) serves the webpack-built `dist/` in containers (multi-stage build); local dev uses webpack-dev-server. Future: static bundles on CDN/S3. |

---

## 3. Backend API

| Method | Endpoint | Purpose |
|---|---|---|
| GET | `/tip` | Return latest tip from Redis cache |
| GET | `/tip/liveness` | Set Redis `trigger=true`; return `200 "liveness check successful"` |
| GET | `/tip/stream` | SSE — stream latest tip from Redis key to client |
| POST | `/chat` | Accept user message |
| GET | `/chat/stream` | SSE — stream assistant reply via LangGraph/LangChain `astream` |

**Design:** FastAPI best practices, modular structure, SOLID, design patterns, `.env` for all secrets.

---

## 4. Feature 1 — Mental Health Tips

1. On load, frontend opens SSE connection and displays a tip.
2. Frontend sends a liveness request every **30s** → backend sets Redis `trigger=true`.
3. **Celery Beat** runs every **5 min** → LangChain (LCEL) task checks `trigger`.
4. If `trigger=true`: generate new tip, append to Redis cache, set `trigger=false`.
5. Cache holds **max 10 tips** (FIFO — oldest removed).
6. Tips shown in a **30% side panel**; main content is the remaining **70%**.

### Cold start & delivery (frontend contract)

- On first load the cache may be empty. `/tip/liveness` triggers an **immediate** deduped worker dispatch (`force=True`) so the first tip is generated in seconds (not up to 5 min).
- **The frontend does NOT poll/retry `/tip`.** `GET /tip` once for an initial value (may be `null` → show a loading state), then open `GET /tip/stream` (SSE). The stream polls Redis (~2s) and pushes a `tip` event as soon as one is available — availability is fully handled server-side.
- The only frontend "retry" responsibility is **SSE reconnection**, which the browser's native `EventSource` does automatically. On reconnect the stream re-emits the current latest tip (per-connection `last_sent_id` resets), so the UI self-heals.

---

## 5. Feature 2 — Chat

1. Chat UI occupies **70%** of screen (`queryapp`).
2. `POST /chat` submits a message; `GET /chat/stream` streams the reply via SSE.
3. Reply generated by a **LangGraph** workflow (single task for now) using **direct `astream`** in the API process.
4. **Conversation memory:** graph compiled with an in-process **`MemorySaver`** checkpointer keyed by `thread_id` (== `session_id`). Gives multi-turn context *within* a session; **volatile** — lost on page refresh / backend restart (acceptable now; no auth/session persistence yet).
5. No DB persistence yet — history also held in frontend state. When auth + DB/RAG land, swap `MemorySaver` for a **persistent, shared checkpointer** (Redis/Postgres) — no call-site changes needed.

### Why two endpoints (POST + GET SSE) — intentional, forward-compatible

The split (`POST /chat` to submit + `GET /chat/stream` for the SSE reply, bridged
through Redis) is **deliberate scaffolding**, not just an `EventSource` GET
work-around. Chat will evolve into a **long-running async workflow** (doc upload
→ ingestion/embedding → hybrid-search RAG → LLM) and eventually a **separate,
independently-scaled service**. That work belongs in a **worker/queue**, at which
point the SSE endpoint must stream output produced in *another* process — which
requires a broker bridge.

- **Today:** `POST` stores the message in Redis (mailbox); `GET /chat/stream`
  claims it (`GETDEL`) and runs `astream` in-process.
- **Future:** `POST` enqueues the workflow task; `GET /chat/stream` subscribes to
  a **Redis Stream / pub-sub** channel where the worker publishes tokens.
- The **two-endpoint contract stays identical for the frontend** across both
  phases — only backend internals change. The current `GETDEL` bridge is a
  stepping stone toward the worker→API streaming bus.
- **Deferred engineering:** the worker→SSE streaming mechanism (Redis Streams /
  Kafka / NATS) is to be designed in the RAG/separate-service phase.

---

## 6. Frontend Layout (single-spa)

- `baseapp` — root-config + `single-spa-layout`; served on a port; mounts parcels.
- `tipsapp` — 30% side panel; SSE tips.
- `queryapp` — 70% chat; SSE chat.
- Loaded via SystemJS import-maps; React + TypeScript + Webpack.

---

## 7. Docker Compose Services

- `nginx` — reverse proxy (`/` → baseapp, `/api` → backend; SSE buffering off)
- `backend` — FastAPI / uvicorn
- `worker` — Celery worker
- `beat` — Celery Beat scheduler
- `redis` — cache + broker
- `baseapp` — frontend shell (only exposed frontend)

`.env` files per service; no hardcoded secrets.

---

## 8. Future Enhancements

1. Database for chat messages and tips.
2. Separate **auth service** (authentication & authorization).
3. File upload → metadata index + S3, chunk + vector DB.
4. RAG via LangGraph (hybrid search → LLM), backed by **Redis Streams / Kafka**.
5. Migrate: Docker Compose → **Kubernetes**; SystemJS → **Module Federation**; deploy on **AWS ECS/ECR**.

### Persistent chat memory (auth phase design)

When auth + a persistent/shared checkpointer (Redis/Postgres) land, chat memory
rehydration splits into two concerns:

- **Stable `thread_id`** — derived from the authenticated user (e.g. `user_id`
  or `user_id:conversation_id`), replacing the current volatile, client-generated
  `session_id`. This is what lets a returning user map back to their history.
- **`GET /chat/history?thread_id=...`** — a new endpoint that reads the persisted
  state once on page load to repaint the transcript, via
  `await graph.aget_state({"configurable": {"thread_id": ...}})` →
  `snapshot.values["messages"]`. No custom message store needed.
- **Streaming unchanged** — SSE keeps emitting only new tokens
  (`on_chat_model_stream`); restored history is model *context*, never re-streamed.

Swap `MemorySaver` → persistent saver at graph compile time; call sites unchanged.

---

## 9. Build Order (agreed first focus)

1. ✅ **docker-compose + nginx + project skeleton + READMEs**
2. ✅ Backend (FastAPI) + Worker (Celery/Beat)
3. Frontend micro-frontends
   - ✅ `baseapp` shell (single-spa root-config + layout, import-maps, Tailwind)
   - ✅ `tipsapp` (30% side panel, SSE tips, Shadow DOM)
   - ⬜ `queryapp` (70% chat, SSE, Shadow DOM)



