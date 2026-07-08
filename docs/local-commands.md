# Local Development — Command Reference

A single place for every command needed to run **Pragmatic-dev** locally on **Windows**
(without Docker), plus the Docker equivalents and handy Redis/debug commands.

> **Prerequisites**
> - Redis running in **WSL2** on `localhost:6379` (see [Redis](#0-redis-wsl2)).
> - Python deps installed via **uv** in `backend/` and `worker/`.
> - Node deps installed via **npm** in each `frontend/*` app.
> - `backend/.env` and `worker/.env` present with `REDIS_HOST=localhost` and a valid
>   `OPENAI_API_KEY` (with model-request permission).

---

## The big picture

Running the full app locally means starting **6 processes**, each in its **own terminal**:

| # | Process | Folder | Purpose |
|---|---------|--------|---------|
| 0 | Redis (WSL2) | — | Cache + Celery broker/back-end |
| 1 | FastAPI backend | `backend/` | API: `/tip`, `/chat`, SSE streams |
| 2 | Celery worker | `worker/` | Executes tasks (LLM calls) |
| 3 | Celery Beat | `worker/` | Schedules the 5-min tip trigger |
| 4 | baseapp (shell) | `frontend/baseapp` | single-spa root-config → port **9000** |
| 5 | tipsapp (MFE) | `frontend/tipsapp` | Tips side panel → port **9001** |

---

## 0. Redis (WSL2)

```powershell
# Start Redis (if not already running)
wsl sudo service redis-server start

# Verify connectivity
wsl redis-cli ping            # -> PONG

# Open an interactive session
wsl redis-cli                 # prompt: 127.0.0.1:6379>
```

**Service management:**

```powershell
wsl sudo service redis-server status     # check if running
wsl sudo service redis-server stop        # stop it
wsl sudo service redis-server restart     # restart it
```

- If `sudo` prompts for a password, it's the Linux user password created during WSL setup.
- To start Redis on boot (only if systemd is enabled in the distro):
  `wsl sudo systemctl enable redis-server`.
- Already inside the Ubuntu/WSL shell? Drop the `wsl` prefix (e.g. `sudo service redis-server start`).

---

## 1. Backend — FastAPI

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\backend
uv run uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

- Health check: <http://localhost:8000/health> → `{"status":"ok","redis":"ok"}`
- API docs (Swagger): <http://localhost:8000/docs>

> ⚠️ `--reload` restarts the server on file save, which **drops open SSE streams**.
> Omit `--reload` when testing long-lived streams.

---

## 2. Celery worker (Windows)

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\worker
celery -A worker.celery_app worker --loglevel=INFO --pool=threads --concurrency=2
```

- ⚠️ **On Windows, do NOT add `--beat`** — Celery's embedded Beat is unsupported on
  Windows (`Error: -B option does not work on Windows`). Run Beat in a **separate
  terminal** (section 3). In **Docker (Linux)** the worker *does* use `--beat`
  (embedded) — that's why the compose command differs from this local one.
- **Use `--pool=threads`** — the workload is I/O-bound (Redis + LLM), so threads give
  concurrent slots cheaply, and the threads pool works fine on Windows.
- If you ever need a single-task pool for debugging, `--pool=solo` also works
  (concurrency ignored). Switch to `prefork` only when CPU-bound tasks are added.

---

## 3. Celery Beat — separate terminal (required on Windows local dev)

Because embedded `--beat` can't run on Windows, start Beat on its own here (in
Docker/Linux this is folded into the worker, so you skip it there):

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\worker
celery -A worker.celery_app beat --loglevel=INFO
```

- No `--pool` flag needed (Beat is a scheduler, not a worker).
- Fires `tips.generate` every **300s (5 min)**; first tick can take up to one full interval.
- `beat: Starting..` **is** the ready state — it's silent between ticks at INFO level.

> 💡 **Faster testing:** set `tip_schedule_seconds=20` in `worker/.env`, clear stale state, and restart Beat:
> ```powershell
> Remove-Item C:\Users\mohanrajsp\Documents\Pragmatic-dev\worker\celerybeat-schedule* -ErrorAction SilentlyContinue
> ```
> Revert to `300` when done.

---

## 4. Frontend — baseapp (shell)

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\baseapp
npm install        # first time only
npm start          # webpack serve --port 9000
```

Opens the single-spa shell at <http://localhost:9000>.

---

## 5. Frontend — tipsapp (MFE)

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\tipsapp
npm install        # first time only
npm start          # webpack serve --port 9001
```

Production build (emits the bundle):

```powershell
npm run build
```

---

## Verify the pipeline without waiting 5 minutes

With the **worker** running, enqueue a tip generation immediately (from a spare terminal):

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\worker
python -u -c "from worker.tasks.tips import generate_tip; print(generate_tip.delay(force=True).get(timeout=60))"
```

- `{'status': 'generated', 'id': '...'}` → worker + LLM are healthy.
- `{'status': 'failed', 'reason': 'permanent_error'}` → LLM auth/quota issue (check worker log).

Trigger a liveness ping (arms the trigger + cold-start dispatch):

```powershell
curl -X POST http://localhost:8000/tip/liveness
```

Watch the tip SSE stream (curl holds long streams reliably, unlike Postman):

```powershell
curl -N http://localhost:8000/tip/stream
```

---

## Redis inspection cheat-sheet

```powershell
wsl redis-cli GET tips:trigger        # "true" = generate on next Beat tick; "false" = skip
wsl redis-cli LLEN tips:list          # number of cached tips (0-10)
wsl redis-cli LRANGE tips:list 0 -1   # dump all cached tips (newest first)
wsl redis-cli LINDEX tips:list 0      # newest tip only
wsl redis-cli GET tips:skip:last      # last "skipped generation" event (JSON) or nil
wsl redis-cli MONITOR                 # live-stream every command hitting Redis (Ctrl+C to stop)
```

> Match the command to the key type: `tips:list` is a **LIST** (`LRANGE`/`LINDEX`/`LLEN`),
> while `tips:trigger` and `tips:skip:last` are **STRINGS** (`GET`).

**`WRONGTYPE` error?** e.g. `GET tips:list` → `WRONGTYPE Operation against a key
holding the wrong kind of value`. `GET`/`SET` only work on **string** keys; a
list needs `LRANGE`/`LINDEX`/`LLEN`. Check a key's type first if unsure:

```powershell
wsl redis-cli TYPE tips:list          # -> list
wsl redis-cli TTL  tips:skip:last     # seconds left (-1 = no expiry, -2 = missing)
```

**Full key reference:**

| Key | Type | Meaning |
|-----|------|---------|
| `tips:list` | list | Cached tips, newest at index 0, capped at 10 |
| `tips:trigger` | string | `"true"` = generate on next Beat tick; `"false"` = skip |
| `tips:skip:last` | string (JSON) | Last skip event relayed to the SSE stream |
| `tips:generation:lock` | string | Present only while a generation is running |
| `tips:retry:in_progress` | string | Present only while a retry chain is active |
| `tips:bootstrap:lock` | string | Short-lived cold-start dedup lock |
| `chat:pending:*` | string | Per-request chat markers |

---

## Docker alternative (whole stack in one command)

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev

# Backend stack (redis + backend + worker + beat + nginx)
docker compose up --build

# Include the frontend shell + MFEs
docker compose --profile frontend up --build
```

- In Docker, `REDIS_HOST=redis` is injected automatically — no `.env` edits needed.
- The worker uses the **threads** pool (`--pool=threads --concurrency=2`) — I/O-bound
  workload, and it behaves the same on Linux and Windows.
- Access via nginx: <http://localhost> (proxies `/api/` → backend).

---

## Quick reference — start everything (local, non-Docker)

Open **7 terminals** and run, in order:

```powershell
# 1) Redis
wsl sudo service redis-server start

# 2) Backend
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\backend; uv run uvicorn app.main:app --reload --port 8000

# 3) Worker  (no --beat on Windows)
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\worker; celery -A worker.celery_app worker --loglevel=INFO --pool=threads --concurrency=2

# 4) Beat  (separate on Windows; embedded via --beat only in Docker/Linux)
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\worker; celery -A worker.celery_app beat --loglevel=INFO

# 5) baseapp
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\baseapp; npm start

# 6) tipsapp
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\tipsapp; npm start

# 7) queryapp (chat)
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev\frontend\queryapp; npm start
```

---

## Push backend/worker images to Amazon ECR

> **Automated path:** `.\scripts\deploy-backend.ps1` does all of this (ensure repos →
> login → build → tag → push, both components). The manual steps below are for
> reference/debugging.

**Context:** registry `498341975274.dkr.ecr.ap-south-1.amazonaws.com`, region
`ap-south-1`, repos `pragmatic-dev/backend` and `pragmatic-dev/worker`.
Requires **Docker Desktop running** (it provides the daemon to both Windows and WSL).

### 1. Authenticate Docker to ECR

```powershell
aws ecr get-login-password --region ap-south-1 | docker login --username AWS --password-stdin 498341975274.dkr.ecr.ap-south-1.amazonaws.com
```

### 2. Build

```powershell
cd C:\Users\mohanrajsp\Documents\Pragmatic-dev
docker build -t pragmatic-dev/backend:latest .\backend
docker build -t pragmatic-dev/worker:latest  .\worker
```

### 3. Tag for the registry

```powershell
docker tag pragmatic-dev/backend:latest 498341975274.dkr.ecr.ap-south-1.amazonaws.com/pragmatic-dev/backend:latest
docker tag pragmatic-dev/worker:latest  498341975274.dkr.ecr.ap-south-1.amazonaws.com/pragmatic-dev/worker:latest
```

### 4. Push

```powershell
docker push 498341975274.dkr.ecr.ap-south-1.amazonaws.com/pragmatic-dev/backend:latest
docker push 498341975274.dkr.ecr.ap-south-1.amazonaws.com/pragmatic-dev/worker:latest
```

### Verify what's in ECR

```powershell
aws ecr describe-images --repository-name pragmatic-dev/backend --region ap-south-1 --query "imageDetails[].imageTags" --output json
aws ecr describe-images --repository-name pragmatic-dev/worker  --region ap-south-1 --query "imageDetails[].imageTags" --output json
```

### ⚠️ Gotcha: `docker login` hangs (Docker Desktop `credsStore`)

On this machine `~/.docker/config.json` has `"credsStore": "desktop"`, so `docker
login` shells out to `docker-credential-desktop.exe`, which **blocks indefinitely
in a non-interactive/background shell** (the script hangs at "Logging Docker in"
and never reaches the build). Diagnosis signature:

```
[aws-getpw]     DONE   # token retrieved fine
[docker-images] DONE   # daemon reachable
[docker-login]  HUNG   # blocks > 40s
```

**Workaround A — inject auth directly (no `docker login`, no helper):**

```powershell
$reg  = "498341975274.dkr.ecr.ap-south-1.amazonaws.com"
$pw   = aws ecr get-login-password --region ap-south-1
$auth = [Convert]::ToBase64String([Text.Encoding]::ASCII.GetBytes("AWS:$pw"))
$cfg  = Join-Path $env:TEMP "ecrcfg"; New-Item -ItemType Directory -Force $cfg | Out-Null
"{`"auths`":{`"$reg`":{`"auth`":`"$auth`"}}}" | Set-Content "$cfg\config.json" -Encoding ascii
$env:DOCKER_CONFIG = $cfg     # build/tag/push in this shell now skip the hanging helper
# ... run steps 2-4 ...
Remove-Item Env:\DOCKER_CONFIG   # restore when done
```

**Workaround B — remove the helper permanently:** edit `~/.docker/config.json`
and delete the `"credsStore": "desktop"` line (creds then stored base64 in
`config.json` instead of the Desktop keychain), then use the normal step 1.

> **Note on long builds:** the image build over the `/mnt/c` mount can exceed 5
> minutes. Run the deploy script / build as a background job and poll **ECR**
> (`describe-images`) as the source of truth, rather than watching the
> BuildKit progress (which buffers when output is redirected to a file).


