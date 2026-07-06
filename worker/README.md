# Pragmatic-dev — Worker

Celery worker + Beat scheduler that generates mental-health tips with a
LangChain **LCEL** pipeline and stores them in Redis for the backend to serve.

> See [`../.github/PLAN.md`](../.github/PLAN.md) for architecture decisions and
> [`../docs/backend-learnings.md`](../docs/backend-learnings.md) for concept notes.

---

## Responsibilities

- Run the `tips.generate` task (contract shared with the backend dispatcher).
- **Beat** triggers generation every `TIP_SCHEDULE_SECONDS` (default 5 min) with
  `force=False` — generating only when the liveness `trigger` flag is set.
- The backend can dispatch the same task with `force=True` for **cold-start**
  (empty cache) so the first tip appears in seconds.
- Store tips in a Redis list (`LPUSH` newest, `LTRIM` to cap at `TIPS_MAX_ITEMS`).

---

## Task contract (`tips.generate`)

| kwarg | Behavior |
|-------|----------|
| `force=True`  | Generate a tip **unconditionally** (cold start / manual). Trigger flag untouched. |
| `force=False` | Generate **only if** the Redis trigger flag is `true` (Beat path); clears the flag afterwards. |

Returns a status dict, e.g. `{"status": "generated", "id": "...", "force": false}`
or `{"status": "skipped", "reason": "trigger_not_set"}`.

---

## Redis storage model (shared with backend)

| Key | Type | Purpose |
|-----|------|---------|
| `tips:list` | list | Tips, newest at index 0 (`LPUSH` + `LTRIM` to 10) |
| `tips:trigger` | string | `"true"`/`"false"` — set by backend liveness, cleared here |

Each stored tip is JSON matching the backend `Tip` schema:
`{"id": "<uuid>", "text": "...", "created_at": <unix_ts>}`.

---

## Project Structure

```
worker/
├── worker/
│   ├── celery_app.py          # Celery app + Beat schedule
│   ├── core/                  # config.py, logging.py
│   ├── llm/                   # base + openai_strategy + factory (strategy pattern)
│   ├── chains/tip_chain.py    # LCEL: prompt -> model -> parser
│   ├── services/
│   │   ├── redis_client.py    # sync Redis client (Celery tasks are sync)
│   │   └── tip_service.py     # add_tip (LPUSH+LTRIM), trigger get/clear
│   └── tasks/tips.py          # @task name="tips.generate"
├── pyproject.toml
├── Dockerfile
└── .env.example
```

---

## Local Development

Requires [uv](https://docs.astral.sh/uv/) and a running Redis.

```powershell
# From worker/
Copy-Item .env.example .env      # then fill in OPENAI_API_KEY
uv sync

# Terminal 1 — the worker (consumes tasks)
uv run celery -A worker.celery_app worker --loglevel=INFO

# Terminal 2 — Beat (schedules periodic generation)
uv run celery -A worker.celery_app beat --loglevel=INFO
```

### Manually trigger a generation (bypasses Beat)

```powershell
uv run python -c "from worker.tasks.tips import generate_tip; print(generate_tip.delay(force=True).id)"
```

---

## Configuration

All env-driven — see [`.env.example`](./.env.example). Key variables:

| Variable | Purpose |
|----------|---------|
| `REDIS_HOST/PORT` | Redis connection (also default broker/backend) |
| `CELERY_BROKER_URL` / `CELERY_RESULT_BACKEND` | Override broker/back-end (else Redis) |
| `TIP_SCHEDULE_SECONDS` | Beat cadence (default 300 = 5 min) |
| `TIPS_MAX_ITEMS` | Max tips retained (FIFO, default 10) |
| `LLM_PROVIDER` / `LLM_MODEL` | Strategy selector + model (default `openai` / `gpt-4o-mini`) |
| `OPENAI_API_KEY` | OpenAI credentials (**never commit**) |

---

## Notes

- Tasks are **synchronous** (Celery worker processes), so we use the sync Redis
  client and `chain.invoke()` (no async needed here).
- `task_acks_late=True` + retries make generation resilient to transient LLM /
  network errors.
- The worker is **self-contained** (its own config + LLM strategy) so it can be
  split into an independent service later without depending on the backend.


