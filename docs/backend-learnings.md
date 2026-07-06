# Backend Learnings — Pragmatic-dev

A running knowledge log built from the questions asked while implementing the
FastAPI backend. Each section explains a concept, why it matters here, and how
it maps to the code in `backend/`.

> Companion to [`.github/PLAN.md`](../.github/PLAN.md) (architecture decisions).
> This file is about **understanding**; the plan is about **decisions**.

---

## Table of Contents

1. [FastAPI application lifecycle (`lifespan` vs middleware)](#1-fastapi-application-lifecycle-lifespan-vs-middleware)
2. [Pydantic `model_config` / settings](#2-pydantic-model_config--settings)
3. [Server-Sent Events (SSE) — how it works](#3-server-sent-events-sse--how-it-works)
4. [SSE heartbeats (`ping=`)](#4-sse-heartbeats-ping)
5. [Celery `send_task` — how the worker is called](#5-celery-send_task--how-the-worker-is-called)
6. [Why offload blocking calls with `asyncio.to_thread`](#6-why-offload-blocking-calls-with-asyncioto_thread)
7. [Redis `GETDEL` — claim-once semantics](#7-redis-getdel--claim-once-semantics)
8. [Cold-start force-trigger (tips)](#8-cold-start-force-trigger-tips)
9. [LangGraph thread config & session isolation](#9-langgraph-thread-config--session-isolation)
10. [LangGraph checkpointers & `MemorySaver`](#10-langgraph-checkpointers--memorysaver)
11. [Does `astream` re-stream history?](#11-does-astream-re-stream-history)
12. [Rehydrating history (persistent-memory phase)](#12-rehydrating-history-persistent-memory-phase)
13. [Why chat uses two endpoints + Redis bridge](#13-why-chat-uses-two-endpoints--redis-bridge)
14. [Celery worker & Beat (tip generation)](#14-celery-worker--beat-tip-generation)
15. [Distributed lock vs `threading.Lock`](#15-distributed-lock-vs-threadinglock)
16. [Celery `self.retry` mechanics](#16-celery-selfretry-mechanics)
17. [Retry storms, single retry chain & task expiry](#17-retry-storms-single-retry-chain--task-expiry)
18. [`@lru_cache` singletons](#18-lru_cache-singletons)
19. [How single-threaded Redis serves multiple services](#19-how-single-threaded-redis-serves-multiple-services)
20. [Config & `.env` pitfalls (pydantic-settings, dotenv, prefixes)](#20-config--env-pitfalls-pydantic-settings-dotenv-prefixes)
21. [Running the stack locally (Redis, hostnames)](#21-running-the-stack-locally-redis-hostnames)

---

## 1. FastAPI application lifecycle (`lifespan` vs middleware)

**Question:** *"FastAPI has a middleware to handle the lifecycle, right?"*

**Key distinction:**
- **Middleware** runs **per request/response** (CORS, auth, logging). It does *not*
  handle app startup/shutdown.
- **Lifecycle (lifespan)** runs **once** — at startup and shutdown (open/close a
  DB or Redis pool). There is no "lifecycle middleware."

**Two ways to do lifespan:**
- `lifespan` async context manager — **modern, recommended** (what we use).
- `@app.on_event("startup"/"shutdown")` — **legacy, deprecated**.

```python
@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    get_redis()          # startup: before yield
    yield
    await close_redis()  # shutdown: after yield

app = FastAPI(lifespan=lifespan)
```

Everything **before `yield`** is startup; **after `yield`** is shutdown. Keeping
both in one function co-locates resource open/close.

**In our code:** `app/main.py`.

---

## 2. Pydantic `model_config` / settings

**Question:** *"What is `model_config` for?"*

`model_config` is **Pydantic v2's configuration** (replaces v1's `class Config`).
For `BaseSettings` it controls **how env vars / `.env` are read**.

```python
model_config = SettingsConfigDict(
    env_file=".env",           # auto-load .env
    env_file_encoding="utf-8",
    case_sensitive=False,      # APP_NAME matches app_name
    extra="ignore",            # ignore unknown env vars
)
```

- `SettingsConfigDict` = settings-specific version of `ConfigDict` (adds
  `env_file`, `env_prefix`, `secrets_dir`, …).
- Precedence: **real env vars > `.env` file > field defaults**.
- This is what makes "no hardcoded secrets" work — e.g. `OPENAI_API_KEY` env var
  auto-populates the `openai_api_key` field.

**In our code:** `app/core/config.py`.

---

## 3. Server-Sent Events (SSE) — how it works

**Question:** *"How does SSE ideally work?"*

SSE = server **pushes** a stream of updates to the browser over **one long-lived
HTTP GET**. One-directional (server → client). Consumed via `EventSource`.

**Mechanics:**
1. Client opens `new EventSource("/api/tip/stream")` (a GET with
   `Accept: text/event-stream`).
2. Server responds `Content-Type: text/event-stream` and **keeps the body open**,
   writing events over time.
3. Event format (fields, terminated by a blank line):
   ```
   event: tip
   data: {"id":"abc","text":"Take a deep breath"}

   : this is a comment / heartbeat
   ```
   | Field | Purpose |
   |-------|---------|
   | `data:` | payload |
   | `event:` | event name (default `message`) |
   | `id:` | stored as `Last-Event-ID` for resume |
   | `retry:` | reconnect delay (ms) |
   | `:` | comment → ignored by client (heartbeat) |

**Killer feature — auto-reconnect:** `EventSource` reconnects automatically on
drop and sends `Last-Event-ID`, so the frontend needs *no* retry logic.

**SSE vs WebSocket vs long-polling:** SSE is ideal for **one-way server pushes**
(tips feed, LLM token streams) — HTTP-native, auto-reconnect, proxy-friendly.
WebSockets are for bidirectional; long-polling is an inefficient legacy fallback.

**Gotchas we handle:** proxy buffering off (nginx), heartbeats for idle timeouts,
`request.is_disconnected()` to stop work when the client leaves, HTTP/2 for the
~6-connection-per-domain limit.

**In our code:** `app/api/routers/tips.py`, `chat.py` (via `sse-starlette`).

---

## 4. SSE heartbeats (`ping=`)

**Question:** *"What is `ping=int(settings.sse_heartbeat_interval)`?"*

Tells `sse-starlette` to send a **keepalive comment** every N seconds:
```
: ping
```
A `:`-prefixed line is an **SSE comment** — the browser ignores it. Its only job
is to put bytes on the wire so **proxies / load balancers / firewalls** don't
kill an idle connection (idle timeouts are often 30–60s; we use 15s).

- `int(...)` because our setting is a `float` but `ping=` wants an int.
- **Two heartbeat styles in our code (intentional):** chat uses the library's
  built-in `ping=`; tips emits its own `{"event": "ping"}` inside its polling
  loop (where a `sleep` already exists). Same goal, placed where each flow fit.

**In our code:** `app/api/routers/chat.py` (`ping=`), `tips.py` (manual ping).

---

## 5. Celery `send_task` — how the worker is called

**Question:** *"How does `send_task` make a call to a worker?"*

**It doesn't call the worker directly.** It's fire-and-forget message passing via
the broker (Redis):

```
Backend                Redis (broker)            Worker
send_task(...)  ──►  LPUSH onto queue   ◄──  BRPOP (blocking pop)
returns instantly     message waits          looks up task name, runs it
```

1. `send_task("tips.generate", kwargs={...})` serializes a **message** (task
   name, id, args) and **pushes it onto a Redis list** (the queue).
2. Returns immediately — backend never talks to the worker. Works even if **no
   worker is running** (message waits in Redis).
3. A separate **worker process** blocking-pops the queue, looks up the task
   **name** in its registry, and executes it.

**Decoupling contract:** producer and consumer only share (a) the **broker URL**
and (b) the **task-name string**. Mental model: *drop a letter in a mailbox*
(Redis), not *phone the recipient* (worker).

**In our code:** `app/services/task_dispatcher.py` (dispatches `tips.generate`).

---

## 6. Why offload blocking calls with `asyncio.to_thread`

**Question:** *"Why spin a separate thread to push the message to Celery?"*

FastAPI runs `async def` handlers on a **single-threaded event loop** that only
switches tasks at `await` points. `Celery.send_task` is **synchronous, blocking
I/O** with no `await` inside.

- ❌ Calling it directly **freezes the whole event loop** for the duration of the
  network I/O — every other request and SSE stream stalls (and the API hangs if
  Redis is slow).
- ✅ `await asyncio.to_thread(fn, ...)` runs the blocking call on a **worker
  thread**; awaiting it **yields control back to the loop**, which stays
  responsive.

**Why a thread works despite the GIL:** Python **releases the GIL during blocking
I/O**, so the loop thread keeps running while the worker thread waits on the
socket. Threads are right for **I/O-bound** blocking (processes for CPU-bound).

**In our code:** `app/services/task_dispatcher.py` → `dispatch_tip_generation`.

---

## 7. Redis `GETDEL` — claim-once semantics

**Question:** *"What is `getdel`?"*

`GETDEL` **reads a key and deletes it atomically**, returning the old value (or
`None`). It's "get-and-consume."

**Why atomic matters:** the naive `GET` then `DELETE` has a **race** — two
requests could both `GET` before either `DELETE`s, processing the same message
**twice** (duplicate LLM calls). `GETDEL` collapses read+delete into one atomic
op on Redis's single-threaded executor → **exactly one** caller wins.

- Gives "claim exactly once" for the pending chat message.
- Requires **Redis 6.2+**.
- Pairs with the TTL on `submit_message` so unclaimed messages auto-expire.

| Command | Behavior |
|---------|----------|
| `GET` | read, leave in place |
| `DEL` | delete, no return |
| **`GETDEL`** | **read + delete atomically** |

**In our code:** `app/services/chat_service.py` → `stream_response`.

---

## 8. Cold-start force-trigger (tips)

**Question / insight:** *"On first load, if the worker already ran and didn't see
the flag, the user waits up to 5 min. If cache is empty, force-trigger the
worker."* — Correct.

**Problem:** empty cache + Beat only runs every 5 min ⇒ first tip could take
minutes.

**Fix (with safeguards):**
1. On `/tip/liveness`, if cache is empty, **dispatch the generation task
   immediately** (`force=True`) instead of waiting for Beat.
2. **De-dup with a `SET NX` lock** (short TTL) so many tabs/users hitting an empty
   cache at once dispatch **one** task (no thundering herd).
3. **`force` flag contract:** immediate dispatch = `force=True` (generate
   unconditionally); Beat = `force=False` (respect the trigger flag).

Two non-conflicting trigger paths: **instant** on cold start (deduped) +
**periodic** (every 5 min while active).

**In our code:** `app/services/tip_service.py` → `ensure_tip_available`;
`app/api/routers/tips.py` (liveness).

---

## 9. LangGraph thread config & session isolation

**Question / insight:** *"We should use a thread config to isolate sessions
between requests."* — Correct.

LangGraph uses `config={"configurable": {"thread_id": ...}}` as the
**isolation/identity key** for a run:
- Separates concurrent sessions (no state bleed).
- Is the **key a checkpointer uses** for memory (see §10) — so adding persistence
  later needs no call-site change.
- Improves tracing (runs grouped per session).

```python
config = {"configurable": {"thread_id": session_id}}
async for event in graph.astream_events(inputs, version="v2", config=config):
    ...
```

**In our code:** `app/services/chat_service.py`.

---

## 10. LangGraph checkpointers & `MemorySaver`

**Questions:** *"Does LangGraph use an in-memory saver here?"* / decision to use
`MemorySaver`.

- **Passing `thread_id` does NOT auto-enable memory.** Without a checkpointer the
  graph runs **stateless**. LangGraph does not silently attach a saver.
- Memory is enabled **only** by compiling with one:
  ```python
  from langgraph.checkpoint.memory import MemorySaver
  builder.compile(checkpointer=MemorySaver())
  ```

**`MemorySaver` traits (chosen for the current phase):**
| Aspect | Behavior |
|--------|----------|
| Storage | in-process RAM |
| Survives restart/refresh? | ❌ volatile (by design here) |
| Shared across replicas? | ❌ per-process (fine — single instance now) |
| Good for | dev, single-instance, "lose context on refresh" |

**Later (auth + DB/RAG):** swap for a **persistent, shared** saver
(Redis/Postgres) — no call-site changes. `MemorySaver` would be wrong for
multi-replica prod (per-process, volatile).

Because `build_chat_graph()` is `@lru_cache`'d, the compiled graph and its
`MemorySaver` are a **process-wide singleton**, so memory persists across
requests for the same `thread_id`.

**In our code:** `app/chains/chat_graph.py`.

---

## 11. Does `astream` re-stream history?

**Question:** *"With persistent memory, does `astream` stream all the messages?"*

**No — only the new reply streams.** Restored history is **input context**, not
**output**:
- Prior turns are fed to the model as prompt context (shape the answer).
- The model **generates** only the new assistant response.
- We filter `on_chat_model_stream`, which fires only for **tokens being generated
  now**.

```python
if event["event"] == "on_chat_model_stream":
    chunk = event["data"]["chunk"]   # only NEW tokens
```

⚠️ This depends on **how** you stream. `astream(..., stream_mode="values")` emits
full **state snapshots** (the whole message list each step). We deliberately use
`astream_events` filtered to `on_chat_model_stream` → new tokens only.

**Also:** frontend keeps the transcript **for display**; it sends only the **new**
message per turn (backend memory supplies context). Two stores, two purposes:
- Backend `MemorySaver` = LLM context.
- Frontend state = rendering the visible chat.

**In our code:** `app/services/chat_service.py`.

---

## 12. Rehydrating history (persistent-memory phase)

**Question / insight:** *"With persistent memory, we need a separate API call to
get past history, then `on_chat_model_stream` for new ones."* — Correct.

When persistent memory + auth land, load splits into two concerns:
| Concern | Mechanism | When |
|---------|-----------|------|
| Load past transcript | `GET /chat/history?thread_id=...` → `graph.aget_state(...)` → `snapshot.values["messages"]` | once, on page load |
| Stream new reply | SSE `on_chat_model_stream` | every turn |

**Prerequisite — a stable `thread_id`:** today's `session_id` is
client-generated and lost on refresh, so it can't map a returning user to their
history. Persistent memory needs a `thread_id` **derived from the authenticated
user** (e.g. `user_id:conversation_id`) — hence an **auth-phase** feature.

**Documented in:** `.github/PLAN.md` → *Persistent chat memory (auth phase)*.

---

## 13. Why chat uses two endpoints + Redis bridge

**Questions:** *"Why two API calls for chat? Why persist to Redis then fetch
again?"* + the vision that chat becomes an async, independently-scaled service.

**Immediate reason:** native `EventSource` (SSE) is **GET-only and cannot send a
body**. To stream via `EventSource`, the request must be a bodyless GET — so the
message goes via `POST` and is handed off to the `GET` stream. Two separate HTTP
requests need a **handoff store** → Redis is a short-lived mailbox
(`SET` + `GETDEL`).

**Strategic reason (why we keep it):** chat will become a **long-running async
workflow** (upload → ingestion/embedding → hybrid-search RAG → LLM) and
eventually a **separate, independently-scaled service**. That work belongs in a
**worker/queue**, at which point the SSE endpoint must stream output produced in
**another process** — which *requires* a broker bridge.

| Today | Future (async / RAG / separate service) |
|-------|------------------------------------------|
| `POST` stores message in Redis | `POST` enqueues workflow task |
| `GET /chat/stream` → `GETDEL` + in-process `astream` | `GET /chat/stream` → subscribe to **Redis Stream / pub-sub** where the worker publishes tokens |
| Redis = mailbox | Redis = worker→API streaming bus |

The **two-endpoint contract stays identical for the frontend**; only backend
internals swap. The current `GETDEL` bridge is a **stepping stone** toward the
worker→API streaming bus. The worker→SSE mechanism (Redis Streams / Kafka / NATS)
is **deferred** to the RAG/separate-service phase.

**In our code:** `app/api/routers/chat.py`, `app/services/chat_service.py`.
**Documented in:** `.github/PLAN.md` → *Why two endpoints*.

---

## 14. Celery worker & Beat (tip generation)

**Context:** the worker is a **separate, self-contained service** that generates
tips and writes them to Redis for the backend to serve.

**Worker vs Beat (two processes, same codebase):**
- **Worker** (`celery ... worker`) — consumes tasks from the queue and executes
  them. Scale horizontally for throughput.
- **Beat** (`celery ... beat`) — the scheduler; periodically *enqueues* a task
  (here, every 5 min). Beat doesn't execute — it just puts a message on the queue
  that a worker then runs. **Run exactly one Beat** to avoid duplicate schedules.

**The `force` flag = two trigger paths, one task:**
```python
@celery_app.task(name="tips.generate")
def generate_tip(self, force=False):
    if not force and not repo.is_triggered():
        return {"status": "skipped"}      # Beat path, no active users
    text = generate_tip_text()            # LCEL invoke
    tip = repo.add_tip(text)
    if not force:
        repo.clear_trigger()              # consume the trigger
```
- **Beat** calls with `force=False` → generate only if a client recently pinged
  liveness (trigger set), then clear the trigger.
- **Backend cold-start** dispatches with `force=True` → generate immediately,
  leave the trigger alone.

**Redis list as a capped feed (`LPUSH` + `LTRIM`):**
```python
pipe.lpush(key, json.dumps(tip))     # newest at index 0
pipe.ltrim(key, 0, max_items - 1)    # keep only the newest N (FIFO)
pipe.execute()                       # atomic pipeline
```
`LPUSH` prepends; `LTRIM` drops everything past the cap → a fixed-size,
newest-first feed. The backend reads index 0 for "latest."

**Reliability knobs:**
- `task_acks_late=True` — the message is acknowledged **after** the task
  finishes, so a crash mid-task re-queues it (at-least-once).
- **Exponential backoff retries, capped** — on transient failures we call
  `self.retry(exc=..., countdown=min(base * 2**retries, max))`, so delays grow
  (10s → 20s → 40s …) up to a cap, bounded by `tip_max_retries` (see §16). On
  exhaustion we catch `MaxRetriesExceededError` and return a clean `failed`
  status instead of crashing.
- **Mutual exclusion (distributed lock)** — the task acquires a non-blocking
  Redis lock at start; if another generation is running it returns
  `{"status": "locked"}`. TTL self-heals on worker death (see §15).
- **Single retry chain** — a `retry-in-progress` marker ensures a fresh task
  (e.g. the next Beat tick) doesn't spawn a *second* parallel retry chain while
  an earlier failure is still retrying (see §17).
- `worker_prefetch_multiplier=1` — don't hoard messages; fairer distribution for
  longer tasks.

**Sync, not async:** Celery worker processes are synchronous, so the worker uses
the **sync** `redis` client and `chain.invoke()` (the backend, being async, uses
`redis.asyncio` and `ainvoke`/`astream`). Same LCEL/strategy patterns, different
execution model.

**In our code:** `worker/worker/celery_app.py` (app + Beat schedule),
`worker/worker/tasks/tips.py` (task), `worker/worker/services/tip_service.py`
(LPUSH/LTRIM/trigger), `worker/worker/chains/tip_chain.py` (LCEL).

---

## 15. Distributed lock vs `threading.Lock`

**Questions:** *"Since Redis is single-threaded, are we not using a thread lock?"*
/ *"What if two threads call `acquire_generation_lock`?"*

**Why not `threading.Lock`:** it lives in **one process's memory** and only
coordinates threads *within that process*. Our concurrency is **across
processes** (Celery `prefork` spawns multiple processes; Beat is separate) and
will be **across containers/machines**. A `threading.Lock` can't see any of that
— it gives false safety. Mutual exclusion must live in **shared external state**
→ Redis.

**Redis single-threadedness is what makes the lock work.** A distributed lock is
just an atomic `SET key <token> NX PX <ttl>` ("set only if absent, with expiry").
Because Redis executes commands **one at a time**, two racing `SET NX` calls are
serialized — exactly one wins, the other sees the key exists:

```
Thread/Process A:  SET lock <tokenA> NX PX ttl   → OK    (acquired)
Thread/Process B:  SET lock <tokenB> NX PX ttl   → nil   (skips → returns None)
```

This holds identically for threads in one process, prefork workers, or separate
containers — all funnel through the same single-threaded Redis.

**Per-lock token protects release.** Each `Lock` has a unique UUID token. Release
is an atomic Lua script: *delete only if the stored token is mine*. So if A's
lock TTL expires and B acquires it, A's late release is a no-op (raises
`LockError`, which we swallow) — A can't delete B's lock.

| | `threading.Lock` | Redis lock (`SET NX`) |
|---|------------------|-----------------------|
| Scope | one process's threads | all processes/machines on shared Redis |
| Works for Celery prefork / containers? | ❌ | ✅ |
| Survives worker crash? | dies with process | ✅ TTL auto-expires |
| Relies on Redis single-thread? | — | ✅ (makes `SET NX` atomic) |

**In our code:** `worker/worker/services/tip_service.py`
(`acquire_generation_lock` / `release_generation_lock`).

---

## 16. Celery `self.retry` mechanics

**Questions:** *"What does `self.retry` do?"* / *"Put a limit on retries."*

`self.retry(...)` (available because the task uses `bind=True`) means **"stop
this run and re-enqueue a fresh copy of me to run again later."** It does **not**
return — it **raises**, aborting the current execution:

- Re-publishes a **new message** for the same task (same args), with
  `self.request.retries` incremented, scheduled after `countdown` seconds.
- **Retries remaining** → raises `Retry` → Celery reschedules.
- **Retries exhausted** (`>= max_retries`) → raises `MaxRetriesExceededError`.

We cap retries with `max_retries` (from `tip_max_retries`) and handle exhaustion
gracefully instead of letting the task error:

```python
try:
    raise self.retry(exc=exc, countdown=countdown)
except MaxRetriesExceededError:
    return {"status": "failed", "reason": "max_retries_exceeded"}
```

- `exc=exc` records the original error (for tracebacks / final failure).
- `countdown=<s>` is the delay; we compute exponential backoff
  `min(base * 2**retries, max)`.

**Mental model:** not a loop or a blocking sleep — the current task exits and a
*new* task run happens later via the broker (fits Celery's distributed model).

**In our code:** `worker/worker/tasks/tips.py`.

---

## 17. Retry storms, single retry chain & task expiry

**Insight:** *"If we retry by re-queuing, won't messages pile up / conflict? And
if the first task fails at minute 1 it must retry — but the second (next tick)
task must not also retry."*

**Queues don't "conflict."** A broker holds many messages by design; each is
processed independently. Duplicate *effects* are already prevented by the **lock**
(no concurrent runs), the **trigger flag** (Beat-path no-ops if already
generated), and the **`LTRIM` cap** (bounded tips). The real risk is **backlog
build-up during an outage**.

**Requirement:** a failed task should retry **quickly** (don't wait 5 min for the
next tick — bad UX), but there must be **only one retry chain at a time** (the
next Beat tick shouldn't start a parallel chain).

**Solution — a `retry-in-progress` marker (Redis key + TTL):**
```python
# Guard: a fresh task (retries == 0) skips if a chain is already active.
if self.request.retries == 0 and service.is_retry_in_progress():
    return {"status": "skipped", "reason": "retry_in_progress"}
...
# On failure: mark the chain, then retry. Continuations (retries > 0) proceed.
service.mark_retry_in_progress(ttl=countdown + buffer)
raise self.retry(exc=exc, countdown=countdown)
```
- `retries == 0` = a fresh task (new Beat tick / cold-start) → **skips** if a
  chain is active.
- `retries > 0` = a continuation of the active chain → **proceeds** (chain keeps
  progressing).
- Marker is **cleared** on success or exhaustion, and its **TTL self-heals** if
  the worker dies mid-chain.

**Timeline (failure at 1:00):**
```
1:00 Beat A fails → mark chain → retry in 10s
1:10 A(retry1) fails → retry in 20s
1:30 A(retry2) succeeds → tip stored, marker cleared      (recovered in ~30s)
5:00 Beat B fires; if A's chain were still active → SKIP  (no parallel chain)
```

**Task expiry (`expires`) — defense-in-depth.** Beat-scheduled messages carry an
`expires` (< the 5-min cadence) so a message that can't run in time is
**discarded** rather than executed late — a newer tick supersedes it. (Retries
are separate messages and unaffected.)

**In our code:** `worker/worker/tasks/tips.py` (guard + marker),
`worker/worker/services/tip_service.py` (marker methods),
`worker/worker/celery_app.py` (Beat `expires`).

---

## 18. `@lru_cache` singletons

**Question:** *"Should `get_redis` be `@lru_cache`'d for singleton?"* — Yes,
where no explicit teardown is needed.

A zero-arg `@lru_cache` function is a clean, thread-safe **process-wide
singleton**: the body runs once, subsequent calls return the cached instance.
CPython guards the call with a lock, so concurrent first-calls won't create two
instances.

We use it for: `get_settings`, `get_redis` (worker), `get_celery_client`
(backend), `build_chat_graph`, `build_tip_chain`, and `configure_logging`
(a zero-arg `None`-returning function → runs its setup exactly once, replacing a
manual `_CONFIGURED` flag).

**When NOT to use it:** when the singleton needs **explicit teardown**. The
backend's async `get_redis` keeps a manual `global _client` + `close_redis()`
because lifespan shutdown must close the connection and reset the reference —
`@lru_cache` can't cleanly release a resource (`cache_clear()` doesn't close it).

**In our code:** `app/core/config.py`, `app/core/logging.py`,
`app/services/task_dispatcher.py`, `worker/worker/services/redis_client.py`,
`app/chains/chat_graph.py`, `worker/worker/chains/tip_chain.py`.

---

## 19. How single-threaded Redis serves multiple services

**Question:** *"If three services rely on Redis, how does a single-threaded Redis
handle requests from all sides?"*

**"Single-threaded" refers to command *execution*, not connections.** Redis
separates two concerns:

1. **Networking** — an **event loop with I/O multiplexing** (`epoll`/`kqueue`)
   holds **thousands of concurrent connections** open. Our backend, worker, and
   beat (each with a small connection *pool*) are just sockets it watches.
2. **Execution** — commands from all connections funnel into **one queue** and
   run **one at a time** on a single core. Each is an in-memory op (microseconds).

```
backend ─┐
worker  ─┼─▶ [ command queue ] ─▶ single executor (µs each) ─▶ reply to that conn
beat    ─┘     (many conns in)        (FIFO, one at a time)
```

**Why one thread is plenty:** a single Redis core does **100k+ ops/sec**; our
load is a handful of ops/sec. Redis is idle almost always.

**The serialization is a feature.** No interleaving mid-command → every op is
**atomic without locks**, which is exactly what makes our patterns correct:
- `SET key token NX PX ttl` (distributed lock) — one racer wins.
- `GETDEL` (chat claim-once) — read+delete can't be split.
- `LPUSH` + `LTRIM` pipeline (capped feed) — runs as a unit.

**Nuances:**
- **Ordering across connections isn't guaranteed** (Redis picks some order), but
  each command is atomic — we never rely on cross-connection ordering.
- **Redis 6+ has multi-threaded *I/O*** (socket read/write), but **execution
  stays single-threaded** — faster byte-moving, same atomicity.
- Scaling far beyond our needs = replicas / Redis Cluster, not threads.

**In our code:** every service talks to the same Redis via `redis_client.py`
(async in backend, sync in worker).

---

## 20. Config & `.env` pitfalls (pydantic-settings, dotenv, prefixes)

Three real startup crashes we hit and fixed — all config/parsing gotchas.

### 20.1 pydantic-settings JSON-decodes "complex" fields before validators

**Symptom:** `SettingsError: error parsing value for field "cors_origins"`.

For a field typed as a **collection** (`list[str]`, `dict`, …), pydantic-settings
tries to **`json.loads` the raw env value** *before* your `field_validator`
runs. So `CORS_ORIGINS=*` (or `a,b`) fails — it isn't valid JSON.

**Fix — `NoDecode`:** annotate the field so pydantic-settings skips JSON decoding
and hands the raw string to your validator:
```python
from typing import Annotated
from pydantic_settings import NoDecode

cors_origins: Annotated[list[str], NoDecode] = Field(default_factory=lambda: ["*"])

@field_validator("cors_origins", mode="before")
@classmethod
def _split_cors(cls, v):            # "a,b" -> ["a", "b"];  "*" -> ["*"]
    return [o.strip() for o in v.split(",") if o.strip()] if isinstance(v, str) else v
```

### 20.2 python-dotenv keeps inline `# comment` as part of the value

**Symptom:** `float_parsing` / `int_parsing` errors like
`input_value='2.0# seconds between…'`.

python-dotenv does **not** strip inline comments — `KEY=2.0# note` yields the
value `"2.0# note"`, which then fails numeric parsing. (Even with a space it's
unreliable across versions.)

**Fix — keep comments on their OWN lines** in `.env` / `.env.example`:
```dotenv
# seconds between Redis reads on the SSE stream
TIP_STREAM_POLL_INTERVAL=2.0
```
Defensive extra: `SettingsConfigDict(str_strip_whitespace=True)` trims stray
whitespace (but does **not** remove mid-value comment text — the own-line rule is
the real fix).

### 20.3 FastAPI router prefix must start with `/`

**Symptom:** `AssertionError: A path prefix must start with '/'`.

`include_router(prefix=...)` asserts a **non-empty** prefix starts with `/`. An
empty string is fine, but a whitespace/comment-corrupted value (from 20.2) is
truthy and fails. Also a value like `api/v1` (no leading slash) fails.

**Fix — normalize + guard:**
```python
prefix = settings.api_prefix.strip()
if prefix and not prefix.startswith("/"):
    prefix = f"/{prefix}"
app.include_router(api_router, prefix=prefix) if prefix else app.include_router(api_router)
```

**In our code:** `app/core/config.py` (`NoDecode`, `str_strip_whitespace`),
`app/main.py` (prefix guard), `backend/.env.example` (own-line comments).

---

## 21. Running the stack locally (Redis, hostnames)

**`REDIS_HOST` differs by run mode:**
- **Docker Compose** → `redis` (the service name; Compose DNS resolves it). The
  compose file sets this via `environment:` so it always wins in containers.
- **Bare-metal / local** (running `uvicorn`/`celery` in a venv) → `localhost`
  (there's no `redis` hostname on the host). Set `REDIS_HOST=localhost` in the
  local `.env`.

**Running Redis on Windows (no Docker):**
| Option | Command | Notes |
|--------|---------|-------|
| **Memurai** (recommended) | `winget install Memurai.MemuraiDeveloper` | Native Windows service on `:6379`, Redis-compatible |
| **WSL** | `wsl --install -d Ubuntu` → `sudo apt install redis-server` → `sudo service redis-server start` | Real Redis; `localhost:6379` forwarded to Windows |
| **Chocolatey** | `choco install memurai-developer -y` | Admin shell |
| **Docker** (later) | `docker run -d -p 6379:6379 redis:7-alpine` | When Docker is installed |

Verify: `redis-cli ping` → `PONG`. Then run backend (`uvicorn app.main:app
--reload`), worker, and beat in separate terminals; `GET /health` should report
`{"status":"ok","redis":"ok"}`.

**In our code:** `backend/.env` / `worker/.env` (`REDIS_HOST`), `docker-compose.yml`
(`environment: REDIS_HOST=redis`), `scripts/smoke-test.ps1`.

---

## Quick reference — where each concept lives

| Concept | File |
|---------|------|
| Lifespan / app factory | `app/main.py` |
| Settings / `model_config` | `app/core/config.py` |
| Logging (`@lru_cache`) | `app/core/logging.py`, `worker/worker/core/logging.py` |
| Tips SSE + heartbeat + cold-start liveness | `app/api/routers/tips.py` |
| Chat two-endpoint bridge + `ping=` | `app/api/routers/chat.py` |
| `GETDEL` bridge, `thread_id`, token streaming | `app/services/chat_service.py` |
| Cold-start dedup + liveness trigger | `app/services/tip_service.py` |
| `send_task` + `asyncio.to_thread` | `app/services/task_dispatcher.py` |
| Redis singleton (manual, for lifespan) | `app/services/redis_client.py` |
| Redis singleton (`@lru_cache`) | `worker/worker/services/redis_client.py` |
| LCEL pipeline + LangGraph + `MemorySaver` | `app/chains/chat_graph.py` |
| LLM strategy pattern | `app/llm/*` and `worker/worker/llm/*` |
| Celery app + Beat schedule + `expires` | `worker/worker/celery_app.py` |
| Tip task: force paths, retry chain, backoff, cap | `worker/worker/tasks/tips.py` |
| Distributed lock, retry marker, LPUSH/LTRIM, trigger | `worker/worker/services/tip_service.py` |
| Tip generation LCEL | `worker/worker/chains/tip_chain.py` |
| Task-name constant (contract) | `worker/worker/constants.py` |

