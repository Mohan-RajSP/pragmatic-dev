# Frontend Learnings — Pragmatic-dev

Concept + config notes for the frontend (micro-frontends with single-spa,
TypeScript, Webpack, Tailwind). Companion to
[`backend-learnings.md`](./backend-learnings.md).

> **Philosophy:** understand *concepts*, look up *config syntax*. Nobody memorizes
> `webpack.config.js`. The transferable knowledge is the mental model; the exact
> option names are a search away.

---

## Table of Contents

1. [Micro-frontends & single-spa](#1-micro-frontends--single-spa)
2. [Applications vs Parcels](#2-applications-vs-parcels)
3. [single-spa-layout (the layout engine)](#3-single-spa-layout-the-layout-engine)
4. [SystemJS & import-maps](#4-systemjs--import-maps)
5. [TypeScript basics for this project](#5-typescript-basics-for-this-project)
6. [`.d.ts` declaration files](#6-dts-declaration-files)
7. [`tsconfig.json`](#7-tsconfigjson)
8. [Webpack](#8-webpack)
9. [Tailwind CSS](#9-tailwind-css)
10. [PostCSS](#10-postcss)
11. [Shadow DOM isolation for MFEs](#11-shadow-dom-isolation-for-mfes)
12. [The one-line cheat-sheet](#12-the-one-line-cheat-sheet)
13. [Building & serving (dev server vs Express)](#13-building--serving-dev-server-vs-express)
14. [API base URL: `/api` (nginx) vs direct backend (local)](#14-api-base-url-api-nginx-vs-direct-backend-local)
15. [Gotcha: import-map CDN paths (single-spa 404)](#15-gotcha-import-map-cdn-paths-single-spa-404)

---

## 1. Micro-frontends & single-spa

**Micro-frontends (MFEs)** split a UI into independently-built, independently-
deployable pieces. **single-spa** is the orchestrator: a small runtime that
mounts/unmounts these pieces into one page.

Our pieces:
- **`baseapp`** — the *root-config* / shell. The only one served on a port. It
  hosts the layout and loads the others.
- **`tipsapp`** — the 30% tips side panel.
- **`queryapp`** — the 70% chat area.

The shell doesn't contain the features — it **composes** them.

---

## 2. Applications vs Parcels

Two ways single-spa mounts a micro-frontend:

| | **Application** | **Parcel** |
|---|---|---|
| Activation | **Route-driven** (URL decides) | **Manual** (parent mounts it in code) |
| Registered? | Yes (`registerApplication`) | No — imported & mounted on demand |
| Rendered by layout engine? | ✅ (`<application>`) | ❌ (mounted imperatively) |
| Best for | Top-level page regions | Reusable/nested widgets, always-on areas |

We use **applications** via the layout engine (both regions always active with a
`<route default>`). Parcels would be the choice for embedding a widget inside
another app's UI.

---

## 3. single-spa-layout (the layout engine)

Instead of manually writing activity functions, we declare the layout once and
let the engine mount each application into its slot.

```html
<!-- microfrontend-layout.html (imported as a raw string) -->
<single-spa-router>
  <div class="flex h-screen">
    <route default>
      <div class="flex-1"><application name="@pragmatic-dev/queryapp"></application></div>
      <aside style="width: var(--panel-width)">
        <application name="@pragmatic-dev/tipsapp"></application>
      </aside>
    </route>
  </div>
</single-spa-router>
```

```ts
const routes = constructRoutes(layoutHtml);          // parse template
const apps   = constructApplications({ routes, loadApp: ({name}) => System.import(name) });
const engine = constructLayoutEngine({ routes, applications: apps });
apps.forEach(registerApplication);
engine.activate();
start();
```

`constructRoutes` also accepts a **JSON object** instead of HTML — we chose HTML
for readability. The engine creates a container `<div id="single-spa-application:NAME">`
for each application and mounts it there.

**In our code:** `frontend/baseapp/src/*`.

---

## 4. SystemJS & import-maps

**SystemJS** is a browser module loader. An **import-map** tells it what URL each
module name resolves to:

```html
<script type="systemjs-importmap">
{ "imports": {
    "single-spa": "https://cdn.../single-spa.min.js",
    "react": "https://cdn.../react.production.min.js",
    "@pragmatic-dev/tipsapp": "//localhost:9001/pragmatic-dev-tipsapp.js"
}}
</script>
```

- MFEs are built as **SystemJS modules** (`libraryTarget: "system"` in Webpack).
- `System.import("@pragmatic-dev/tipsapp")` fetches that URL and returns the
  module (its single-spa lifecycles).
- Shared libs (`react`, `single-spa`) are listed **once** here, so every MFE uses
  the **same instance** (not a bundled copy each) — smaller, and React stays a
  singleton.
- `import-map-overrides` lets you repoint a module at runtime (great for testing
  one MFE against prod).

Chosen for now over **Module Federation** (a more modern Webpack-native approach)
— migrating later won't change the backend/nginx contract.

---

## 5. TypeScript basics for this project

TypeScript = JavaScript + **types checked at compile time**. Same JS you know,
with annotations that catch bugs before runtime.

```ts
interface Tip { id: string; text: string; createdAt: number; }
function addTip(tip: Tip, tips: Tip[]): Tip[] { return [tip, ...tips]; }
```

React props/state:
```tsx
interface PanelProps { width: number; }
const Panel: React.FC<PanelProps> = ({ width }) => <div style={{ width }} />;
```

The payoff for MFEs: shared data shapes (SSE messages, parcel props) are typed,
so mistakes across the app boundaries surface immediately.

---

## 6. `.d.ts` declaration files

A **declaration file** holds *only types, no runtime code* — it describes things
to the compiler. Vanishes at build time.

```ts
// declarations.d.ts — teach TS that importing .html/.css yields these types
declare module "*.html" { const s: string; export default s; }
declare module "*.css"  { const sheet: CSSStyleSheet; export default sheet; }
```

Needed because TS only knows `.ts`/`.js`. When we `import x from "./file.html"`,
this tells TS the type; a matching **Webpack loader** provides the actual value
at build time. **TS declaration + Webpack loader are two halves of one deal.**

---

## 7. `tsconfig.json`

The TypeScript compiler's rulebook. Ones that matter:

| Option | Meaning |
|--------|---------|
| `strict: true` | All strict checks on — the main reason to use TS |
| `lib: ["DOM", ...]` | Which built-in APIs exist (`DOM` → `document`, `window`) |
| `noEmit: true` | TS only *type-checks*; Webpack/ts-loader emits the JS |
| `moduleResolution: "Bundler"` | Resolve imports like a bundler does |
| `resolveJsonModule` | Allow `import x from "./x.json"` |
| `types: ["systemjs"]` | Add global typings (the `System` object) |

---

## 8. Webpack

A **bundler**: starts at an entry file, follows every import, transforms each
file type via **loaders**, and outputs browser-ready bundles.

```js
entry: "src/....ts",
output: { filename: "....js", libraryTarget: "system" },  // SystemJS module
module: { rules: [
  { test: /\.tsx?$/, use: "ts-loader" },                   // TS → JS
  { test: /\.html$/, type: "asset/source" },                // file → string
  { test: /\.css$/, use: ["style-loader","css-loader","postcss-loader"] },
]},
externals: ["single-spa","react","react-dom", /^@pragmatic-dev\//], // from import-map
devServer: { port: 9000 },
```

- **loaders** = "for this file type, do this." CSS chain runs **right → left**:
  `postcss-loader` (Tailwind) → `css-loader` (resolve imports) → `style-loader`
  (inject `<style>`).
- **`externals`** = "don't bundle these; provided at runtime" (import-map libs).
- **`libraryTarget: "system"`** = output a SystemJS module (loaded via import-map).
- **`devServer`** = local hot-reloading server.

---

## 9. Tailwind CSS

Utility-class CSS framework — compose classes in markup instead of writing CSS:

```html
<div class="flex h-screen bg-gray-50 p-4">   <!-- display:flex; height:100vh; ... -->
```

`tailwind.config.js`:
```js
content: ["./src/**/*.{ts,tsx,html}"],  // scan these for class names (on-demand generation)
theme: { extend: { colors: { brand: "#4f46e5" } } },  // add design tokens
```

- **`content`** is critical: Tailwind only generates classes it *finds* in these
  files → tiny CSS. Forget to list a file → its classes won't exist.
- **`theme.extend`** adds tokens (e.g. `bg-brand`) without dropping defaults.

---

## 10. PostCSS

A CSS transformer that runs **plugins**. Tailwind *is* a PostCSS plugin.

```js
// postcss.config.js
plugins: { tailwindcss: {}, autoprefixer: {} }
```
- `tailwindcss` — expands `@tailwind base/components/utilities;` into real CSS.
- `autoprefixer` — adds `-webkit-`/`-moz-` prefixes for browser support.

Flow: `@tailwind` CSS → PostCSS (Tailwind + autoprefixer) → css-loader → page.

---

## 11. Shadow DOM isolation for MFEs

Each MFE renders inside its own **Shadow DOM** so its CSS can't leak in or out —
critical when `tipsapp` and `queryapp` render side-by-side in the shell.

Mechanics:
1. On mount, `container.attachShadow({ mode: "open" })`.
2. Inject the MFE's compiled Tailwind **inside** the shadow root
   (`shadow.adoptedStyleSheets = [sheet]`) — global `<head>` styles don't pierce
   the boundary, so each MFE carries its own.
3. Render React into a `<div>` inside the shadow root.

Notes:
- **React 17+** required (event delegation works inside shadow roots).
- **CSS variables pierce** the boundary → shared theme tokens still work.
- **Portals** (modals/menus to `document.body`) escape the shadow root — render
  them into an in-shadow container if you need styles.

**In our code:** `frontend/tipsapp/src/pragmatic-dev-tipsapp.tsx` (shadow mount +
`adoptedStyleSheets`).

---

## 12. The one-line cheat-sheet

| Thing | Remember only this |
|-------|--------------------|
| single-spa | "runtime that mounts MFEs into one page" |
| application vs parcel | "route-driven vs manually-mounted" |
| single-spa-layout | "declare the layout; engine mounts apps into slots" |
| import-map | "module name → URL; shared libs listed once" |
| `libraryTarget: system` | "build as a SystemJS module" |
| `tsconfig` | "TypeScript's rulebook (`strict` matters)" |
| `.d.ts` | "tells TS about non-code imports" |
| webpack loaders | "per-file-type transforms; CSS chain right→left" |
| `externals` | "don't bundle; provided by import-map" |
| tailwind `content` | "where Tailwind scans for class names" |
| postcss | "runs Tailwind + autoprefixer" |
| Shadow DOM | "per-MFE CSS isolation; inject styles inside the root" |

> If it's **config** → look it up. If it's a **concept** → understand it once.

---

## 13. Building & serving (dev server vs Express)

Two distinct ways each frontend runs — don't confuse them:

| | **Local dev** | **Container / prod-like** |
|---|---|---|
| Command | `npm start` (webpack-dev-server) | `npm run build` → `node server.js` |
| Output | compiled in memory | static files in `dist/` |
| Hot reload | ✅ | ❌ |
| Server | webpack-dev-server | **Express** |

**Why a build step for containers:** webpack-dev-server is a *development* tool
(in-memory, unoptimized). For a deployable image you **build once**
(`webpack --mode=production` → minified static bundle) and serve the files.

**Why Express:** an all-Node server that serves `dist/`; the shell can later
inject/serve the **import-map dynamically** per environment rather than
hard-coding it — handy for pointing MFEs at different URLs per env.

**Multi-stage Docker build:**
```dockerfile
FROM node:20-alpine AS build          # stage 1: build
RUN npm install && npm run build      #   → dist/

FROM node:20-alpine AS runtime        # stage 2: serve
RUN npm install --omit=dev            #   only express (prod dep)
COPY --from=build /app/dist ./dist
CMD ["node", "server.js"]             #   Express serves ./dist
```
Stage 2 drops all build tooling → smaller, safer image with just Express + the
static bundle.

**The Express servers:**
- `baseapp/server.js` — serves `dist/` + SPA fallback to `index.html`.
- `tipsapp/server.js` — serves the `dist/` JS bundle with CORS (shell loads it
  cross-origin via the import-map). No HTML — it's just a module.

**Future:** MFE bundles are ultimately static assets → a CDN / S3 is even more
common than a running server. Express is the container-friendly middle ground.

---

## 14. API base URL: `/api` (nginx) vs direct backend (local)

The tipsapp calls the backend for tips (`/tip`, `/tip/history`, `/tip/stream`,
`/tip/liveness`). **Where** those requests go depends on how you're running:

> ✅ **Note (2026-07-08):** the `pragmatic-dev.in` domain is **verified** and
> hosting has resumed. In prod the SPA is served from CloudFront at
> `app.pragmatic-dev.in` and calls the backend at `api.pragmatic-dev.in`, with
> **DNS on GoDaddy** (`app`/`api` CNAMEs, apex forwarding — no Route 53). Local
> dev still uses the direct `localhost:8000` path below (see
> [`deployment-plan.md`](./deployment-plan.md)).

| Setup | Page origin | API base | Why |
|-------|-------------|----------|-----|
| **Local dev** (no nginx) | `http://localhost:9000` (shell) | `http://localhost:8000` | Talk to FastAPI **directly**; there's no proxy to add `/api`. |
| **Containerized / prod** | `http://localhost` / `pragmatic-dev.in` | `/api` | nginx routes `/api/*` → `backend:8000/*` (strips the prefix). |

**Key insight — the backend has NO `/api` prefix.** Its routes are `/tip`,
`/chat`, etc. (`api_prefix = ""`). The `/api` segment is **purely an nginx
convention** so one origin can serve both the frontend (`/`) and the API
(`/api/`). nginx's `proxy_pass http://backend:8000/;` (trailing slash) strips it:

```
browser → /api/tip/stream → nginx → backend:8000/tip/stream
```

**The bug this caused:** with the base hard-set to `/api`, running locally made
the tipsapp request `http://localhost:9000/api/tip/stream` — i.e. the **baseapp
Express server**, which knows nothing about `/api` → 404. There's no nginx
locally to do the rewrite.

**The fix (`tipsapp/src/config.ts`):** default the base to the backend origin and
keep a runtime override for nginx/prod:

```ts
export const API_BASE =
  window.__TIPS_API_BASE__ ?? "http://localhost:8000"; // local dev default
// In the nginx/prod shell, set window.__TIPS_API_BASE__ = "/api" before load.
```

- **Same bundle, every environment** — no rebuild needed; the shell injects the
  override per environment.
- **CORS:** cross-origin calls (`:9000`/`:9001` → `:8000`) work because the
  backend sets `cors_origins = ["*"]` in dev. `EventSource` (SSE) and the
  header-less `POST /tip/liveness` are "simple" requests, so no preflight.
- **Takeaway:** the frontend should never assume a proxy exists. Make the API
  base **configurable**, default it to what works with zero infra (direct
  backend), and let the proxy path be an explicit override.

---

## 15. Gotcha: import-map CDN paths (single-spa 404)

Shared libs (`single-spa`, `react`, `react-dom`) are loaded from a CDN via the
SystemJS import-map in `baseapp/src/index.ejs`. **SystemJS needs the `system`
module format** — but a package's published folder layout is not guessable.

**What broke:** `single-spa@6.0.1/lib/**system**/single-spa.min.js` → **404**.
The package actually nests the format under an ES-target folder:

```
/lib/es5/system/single-spa.min.js       ✅  (use this — widest browser support)
/lib/es2015/system/single-spa.min.js    ✅
/lib/system/single-spa.min.js           ❌  (does not exist)
```

**How to find the real path** (don't guess) — query the jsdelivr data API:

```powershell
# List the actual files that ship in a version
(Invoke-RestMethod "https://data.jsdelivr.com/v1/packages/npm/single-spa@6.0.1?structure=flat").files.name -match 'min\.js$'
```

**Learnings:**
- SystemJS import-map entries must point at the **`system`** build of a lib, not
  `esm`/`umd`/`cjs`. (React is the exception here — it has no `system` build, so
  we load its **`umd`** bundle and rely on SystemJS's `amd` + `named-exports`
  extras to consume it.)
- CDN 404s **cache in the browser** ("404 from disk cache"). After fixing a URL,
  **hard-refresh** (`Ctrl+Shift+R`) or disable cache — a normal reload keeps
  serving the cached failure.
- `index.ejs` is compiled into `dist/index.html` at build time, so after editing
  the import-map you must **rebuild** (`npm run build`) for `node server.js` to
  serve the change (webpack-dev-server / `npm start` picks it up automatically).

**In our code:** `frontend/baseapp/src/index.ejs` (import-map + SystemJS extras).



