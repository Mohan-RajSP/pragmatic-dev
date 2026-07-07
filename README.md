# Pragmatic-dev

A learning-focused monolithic-but-modular application (designed to grow into
microservices) with two features:

1. **Mental-health tips** — a Celery worker generates tips on a schedule; the
   FastAPI backend serves the latest via REST + SSE to a side panel.
2. **Chat** — streams LLM replies token-by-token over SSE using LangGraph.

Frontend uses **micro-frontends** (single-spa). Everything is containerized with
Docker Compose (→ Kubernetes later), destined for AWS ECS/ECR.

> 📋 Architecture decisions: [`.github/PLAN.md`](./.github/PLAN.md)
> 📚 Concept notes / learnings: [`docs/backend-learnings.md`](./docs/backend-learnings.md)

---

## Architecture

```
                         ┌────────────── nginx (:80) ──────────────┐
Browser  ───────────────▶│  /      → baseapp (single-spa shell)     │
                         │  p → backend (FastAPI)  [SSE-safe]  │
                         └───────────────────┬──────────────────────┘
                                             │
                 ┌───────────────────────────┼───────────────────────────┐
                 ▼                            ▼                           ▼
            backend (FastAPI)            redis (cache +            worker + beat
            /tip /tip/liveness           broker/back-end)          (Celery: tips.generate)
            /tip/stream (SSE)                  ▲                          │
            /chat /chat/stream (SSE)           └──── LPUSH/LTRIM tips ─────┘
```

- **backend** reads tips from Redis and streams them; runs chat via LangGraph `astream`.
- **worker** generates tips (LCEL → LLM) and writes them to Redis.
- **beat** enqueues periodic tip generation; backend also dispatches a cold-start job.
- **nginx** is the single entry point (reverse proxy, SSE-friendly).

---

## Services (docker-compose)

| Service | Purpose | Port |
|---------|---------|------|
| `nginx` | Reverse proxy (`/` → baseapp, `/api` → backend) | **80** (published) |
| `backend` | FastAPI app | 8000 (also published for dev) |
| `worker` | Celery worker (consumes `tips.generate`) | — |
| `beat` | Celery Beat scheduler | — |
| `redis` | Cache + Celery broker/back-end | — |
| `baseapp` | single-spa shell (profile `frontend`, built later) | 9000 |

---

## Quick start

### 1. Create env files (secrets)

```powershell
Copy-Item backend\.env.example backend\.env
Copy-Item worker\.env.example  worker\.env
# Edit both and set OPENAI_API_KEY (and any overrides).
```

> Compose treats these `.env` files as optional (`required: false`) so the stack
> still boots without them — but the LLM features need `OPENAI_API_KEY`.

### 2. Bring up the backend stack

```powershell
docker compose up --build
```

This starts **redis + backend + worker + beat + nginx**. Once healthy:

- API via nginx:  http://localhost/api/health
- API direct:     http://localhost:8000/health
- API docs:       http://localhost:8000/docs

### 3. (Later) include the frontend shell

Once `frontend/baseapp` has its Dockerfile:

```powershell
docker compose --profile frontend up --build
# App shell: http://localhost/
```

---

## Endpoints (through nginx, prefixed with /api)

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/health` | Service + Redis health |
| GET | `/api/tip` | Latest mental-health tip |
| POST | `/api/tip/liveness` | Liveness ping (triggers/force-starts tips) |
| GET | `/api/tip/stream` | SSE stream of the latest tip |
| POST | `/api/chat` | Submit a chat message |
| GET | `/api/chat/stream` | SSE stream of the assistant reply |

---

## Repository layout

```
Pragmatic-dev/
├── backend/            # FastAPI service (see backend/README.md)
├── worker/             # Celery worker + Beat (see worker/README.md)
├── frontend/           # single-spa micro-frontends
│   ├── baseapp/        # shell / root-config (served)
│   ├── tipsapp/        # tips side panel (parcel)
│   └── queryapp/       # chat (parcel)
├── nginx/nginx.conf    # reverse proxy config
├── docker-compose.yml
├── docs/               # learning notes
└── .github/PLAN.md     # architecture decisions (authoritative)
```

---

## Notes

- **Secrets** live only in `.env` files (git-ignored). Nothing is hardcoded.
- **SSE** routes are proxied with buffering disabled and long read timeouts.
- The stack is designed to split into microservices later (backend and worker
  are already self-contained with their own configs).

