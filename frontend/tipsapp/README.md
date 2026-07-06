# Pragmatic-dev — tipsapp (mental-health tips panel)

A React + TypeScript **single-spa micro-frontend** that renders the **30% side
panel** of tips. It's mounted by the `baseapp` shell (via the layout engine) and
renders inside its own **Shadow DOM** for full CSS isolation.

> See [`../../docs/frontend-learnings.md`](../../docs/frontend-learnings.md) for concepts.

---

## What it does

1. On mount, fetches the latest tip once (`GET /api/tip`) — may be empty on a
   cold cache (shows a loading state).
2. Opens an **SSE** stream (`GET /api/tip/stream`) and prepends each new tip
   (deduped by id, capped at 10, newest first). The browser auto-reconnects.
3. Sends a **liveness** ping (`GET /api/tip/liveness`) immediately and every
   **30s**, which triggers fresh generation / cold-start on the backend.

The panel **never polls** `/tip` — the stream delivers updates.

---

## Key implementation details

- **Shadow DOM isolation** — `pragmatic-dev-tipsapp.tsx` attaches a shadow root
  to the container and injects the compiled Tailwind as a **constructable
  stylesheet** (`adoptedStyleSheets`) *inside* it. Styles can't leak in/out; CSS
  variables (theme tokens) still pierce the boundary.
- **`single-spa-react`** provides the `bootstrap`/`mount`/`unmount` lifecycles.
- **SystemJS module** output (`libraryTarget: "system"`), loaded by the shell's
  import-map at `//localhost:9001/pragmatic-dev-tipsapp.js` in dev.
- `react`, `react-dom`, `single-spa` are **externals** (shared via import-map).

---

## Structure

```
tipsapp/
├── src/
│   ├── pragmatic-dev-tipsapp.tsx  # single-spa lifecycles + Shadow DOM mount
│   ├── TipsPanel.tsx              # the React UI (header, tip cards, states)
│   ├── useTips.ts                 # hook: initial fetch + SSE + 30s liveness
│   ├── api.ts                     # backend calls (fetch tip, liveness, open SSE)
│   ├── config.ts · types.ts       # API endpoints, intervals, caps · Tip type
│   ├── types.ts                   # Tip type
│   ├── styles/tailwind.css        # @tailwind directives (→ constructable sheet)
│   └── declarations.d.ts          # *.css → CSSStyleSheet typing
├── webpack.config.js · tsconfig.json · tailwind.config.js · postcss.config.js
└── Dockerfile
```

---

## Local development

```powershell
# From frontend/tipsapp
npm install
npm start          # webpack dev server on :9001
```

Run alongside the `baseapp` shell (`:9000`) and the backend (via nginx). The
shell's import-map loads this bundle and mounts it into the 30% panel.

API calls use relative `/api/*`, so they resolve through nginx. For standalone
dev without nginx, set `window.__TIPS_API_BASE__` (see `config.ts`).

---

## Docker / Compose

Built under the `frontend` profile in the root `docker-compose.yml`. The image
is a **multi-stage build**: webpack builds the SystemJS bundle, then an
**Express server** (`server.js`) serves `dist/` with CORS on `:9001`.

```powershell
docker compose --profile frontend up --build
```

> Local dev uses `npm start` (webpack-dev-server, hot reload); the container uses
> `npm run build` + `node server.js` (built bundle served by Express).



