# Pragmatic-dev — baseapp (single-spa shell)

The **root-config** (shell) micro-frontend. It's the only frontend served on a
port; it hosts the **single-spa-layout** engine and mounts the other MFEs
(`tipsapp`, `queryapp`) as applications loaded via **SystemJS import-maps**.

> See [`../../.github/PLAN.md`](../../.github/PLAN.md) for frontend architecture decisions.

---

## Responsibilities

- Define the **import-map** (how SystemJS resolves each MFE + shared `react`).
- Declare the **layout** (30% tips side panel / 70% chat) in
  `src/microfrontend-layout.html`.
- Register + activate the applications and `start()` single-spa.
- Provide **shared design tokens** as CSS variables (they pierce the MFE Shadow
  DOM boundaries, so parcels stay visually consistent while CSS-isolated).

The shell itself renders minimal chrome; the tips/query MFEs own their UI and
isolate their Tailwind inside their own shadow roots.

---

## Tech

- **TypeScript**, **Webpack** (SystemJS `libraryTarget: "system"` output)
- **single-spa** + **single-spa-layout**
- **Tailwind CSS** (shell chrome only) via PostCSS

---

## Structure

```
baseapp/
├── src/
│   ├── index.ejs                    # HTML shell + SystemJS import-map + tokens
│   ├── pragmatic-dev-root-config.ts # constructRoutes/Applications/LayoutEngine
│   ├── microfrontend-layout.html    # declarative 30/70 layout
│   ├── styles/global.css            # Tailwind (shell chrome)
│   └── declarations.d.ts            # *.html raw-string import typing
├── webpack.config.js
├── tsconfig.json
├── tailwind.config.js / postcss.config.js
└── Dockerfile
```

---

## Local development

```powershell
# From frontend/baseapp
npm install
npm start          # webpack dev server on http://localhost:9000
```

The shell expects the parcels at (dev import-map defaults):
- `tipsapp`  → http://localhost:9001
- `queryapp` → http://localhost:9002

Until those MFEs exist, the shell loads but their regions stay empty (SystemJS
will 404 those modules) — that's expected during this phase.

### Import-map overrides
The page includes `import-map-overrides`. Set `localStorage.devtools = true` to
reveal the UI and repoint any MFE to a different URL at runtime.

---

## Docker / Compose

Built under the `frontend` profile in the root `docker-compose.yml`. The image
is a **multi-stage build**: webpack builds the static bundle, then an **Express
server** (`server.js`) serves `dist/` (with SPA fallback) on `:9000`.

```powershell
docker compose --profile frontend up --build
# Shell via nginx: http://localhost/
```

nginx proxies `/` → `baseapp:9000` and `/api` → the backend.

> Local dev uses `npm start` (webpack-dev-server, hot reload); the container uses
> `npm run build` + `node server.js` (built bundle served by Express).

---

## Notes

- Output is a **SystemJS module** (not a standalone bundle) — it's loaded through
  the import-map, like the MFEs.
- `single-spa`, `react`, and `@pragmatic-dev/*` are **externals** (provided via
  the import-map), so they aren't bundled into the shell.
- Migrating to **Webpack Module Federation** later won't change this contract for
  the backend/nginx.

