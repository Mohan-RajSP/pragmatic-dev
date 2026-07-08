/**
 * Tech-stack showcase — a floating button that opens a scrollable modal
 * explaining the technologies and architecture behind this app.
 *
 * Lives in the shell (baseapp) because it describes the *whole product*, not a
 * single MFE. Built with vanilla DOM (the shell isn't a React app) using
 * Tailwind utility classes from the shell's global stylesheet. All class names
 * are written as literals so Tailwind's content scanner generates them.
 */

interface TechItem {
  name: string;
  desc: string;
}
interface TechSection {
  title: string;
  icon: string;
  items: TechItem[];
}

const INTRO =
  "A micro-frontend mental-health companion — live well-being tips plus a " +
  "streaming AI chat — engineered as a modular monolith that can split into " +
  "microservices as it grows.";

const SECTIONS: TechSection[] = [
  {
    title: "Frontend",
    icon: "🎨",
    items: [
      { name: "React 18 + TypeScript", desc: "Component-based, fully type-safe UI for the two micro-frontends (tips + chat)." },
      { name: "single-spa", desc: "Micro-frontend orchestrator that mounts independently built apps into one shell." },
      { name: "single-spa-layout", desc: "Declarative layout that slots each MFE into its screen region (70% chat / 30% tips)." },
      { name: "SystemJS + import-maps", desc: "Runtime module loader; React & single-spa are shared as singletons across MFEs." },
      { name: "Webpack", desc: "Bundles each MFE as a standalone SystemJS module, deployable on its own." },
      { name: "Tailwind CSS + Shadow DOM", desc: "Utility-first styling compiled inside each MFE's shadow root, so CSS never collides." },
      { name: "Server-Sent Events (SSE)", desc: "One-way streaming for live tips and token-by-token chat responses." },
    ],
  },
  {
    title: "Backend API",
    icon: "⚙️",
    items: [
      { name: "FastAPI", desc: "Async Python framework serving REST + SSE endpoints for tips and chat." },
      { name: "Pydantic v2 + pydantic-settings", desc: "Typed schemas/validation and 12-factor env-driven config (no hardcoded secrets)." },
      { name: "Uvicorn", desc: "High-performance ASGI server running the app." },
      { name: "Custom exception handling", desc: "Uniform error contracts, including graceful degradation when the cache drops mid-stream." },
    ],
  },
  {
    title: "AI / LLM orchestration",
    icon: "🧠",
    items: [
      { name: "LangChain (LCEL)", desc: "Composable prompt | model | parser pipelines with each step kept distinct." },
      { name: "LangGraph", desc: "Stateful chat workflow with per-session memory via an in-process checkpointer." },
      { name: "Strategy pattern", desc: "Swap the LLM provider/model purely through configuration." },
      { name: "Builder pattern", desc: "Assembles prompt context (e.g. recent-tips history to avoid duplicates)." },
      { name: "OpenAI GPT-4o-mini", desc: "The underlying model generating tips and chat replies." },
    ],
  },
  {
    title: "Async processing",
    icon: "🔄",
    items: [
      { name: "Celery", desc: "Distributed task queue running background tip generation off the request path." },
      { name: "Celery Beat", desc: "Cron-like scheduler that triggers fresh tip generation every 5 minutes." },
      { name: "Thread pool + retries", desc: "I/O-bound concurrency for LLM calls, with exponential backoff and permanent-vs-transient error classification." },
    ],
  },
  {
    title: "Data & caching",
    icon: "🗄️",
    items: [
      { name: "Redis", desc: "Celery broker/result backend plus app cache: capped tips list, liveness trigger, chat hand-off bridge, and distributed locks." },
    ],
  },
  {
    title: "Infrastructure & DevOps",
    icon: "🐳",
    items: [
      { name: "Docker & Docker Compose", desc: "Reproducible multi-service orchestration for local development." },
      { name: "nginx", desc: "Reverse proxy routing /api to the backend, tuned to keep SSE streams open." },
      { name: "uv", desc: "Fast, reproducible Python dependency management." },
    ],
  },
  {
    title: "Cloud & deployment (AWS)",
    icon: "☁️",
    items: [
      { name: "ECS Fargate", desc: "Serverless containers for the backend and Celery worker." },
      { name: "S3 + CloudFront", desc: "Static MFE bundles served globally via CDN." },
      { name: "ElastiCache", desc: "Managed Redis in production." },
      { name: "Route 53 + ACM", desc: "DNS (app./api. subdomains) and TLS certificates." },
      { name: "ECR", desc: "Registry for the backend/worker container images." },
    ],
  },
  {
    title: "Architecture & principles",
    icon: "🧩",
    items: [
      { name: "Micro-frontends", desc: "Independently built and deployed UI slices composed at runtime." },
      { name: "Monolith → microservices", desc: "Modular boundaries today, designed to split into services later." },
      { name: "SOLID + design patterns", desc: "Strategy, Builder, dependency injection, and single-responsibility modules throughout." },
      { name: "Streaming-first UX", desc: "SSE delivers real-time tips and chat for a responsive feel." },
    ],
  },
];

function renderSections(): string {
  return SECTIONS.map(
    (s) => `
    <section class="mb-6 last:mb-0">
      <h3 class="mb-3 flex items-center gap-2 text-xs font-bold uppercase tracking-wider text-brand">
        <span class="text-base">${s.icon}</span> ${s.title}
      </h3>
      <ul class="space-y-2">
        ${s.items
          .map(
            (it) => `
          <li class="rounded-lg border border-gray-100 bg-gray-50 p-3">
            <p class="text-sm font-semibold text-gray-800">${it.name}</p>
            <p class="mt-0.5 text-xs leading-relaxed text-gray-500">${it.desc}</p>
          </li>`,
          )
          .join("")}
      </ul>
    </section>`,
  ).join("");
}

/** Build + mount the floating button and its modal (idempotent). */
export function mountTechStack(): void {
  if (document.getElementById("tech-stack-fab")) return;

  // --- Floating action button ---
  const btn = document.createElement("button");
  btn.id = "tech-stack-fab";
  btn.type = "button";
  btn.className =
    "fixed bottom-4 right-4 z-[60] flex items-center gap-2 rounded-full bg-brand px-4 py-2.5 " +
    "text-sm font-semibold text-white shadow-lg transition-transform hover:scale-105 hover:bg-brand-dark " +
    "focus:outline-none focus:ring-2 focus:ring-brand focus:ring-offset-2";
  btn.innerHTML = `<span aria-hidden="true">🧱</span><span>Tech stack</span>`;
  btn.setAttribute("aria-haspopup", "dialog");

  // --- Modal overlay ---
  const overlay = document.createElement("div");
  overlay.id = "tech-stack-overlay";
  overlay.className =
    "fixed inset-0 z-[70] hidden items-center justify-center bg-black/50 p-4 backdrop-blur-sm";
  overlay.setAttribute("role", "dialog");
  overlay.setAttribute("aria-modal", "true");
  overlay.setAttribute("aria-label", "Technology stack");
  overlay.innerHTML = `
    <div class="flex max-h-[85vh] w-full max-w-2xl flex-col overflow-hidden rounded-2xl bg-white shadow-2xl">
      <div class="flex items-start justify-between gap-4 bg-gradient-to-r from-brand to-brand-dark px-6 py-4">
        <div>
          <h2 class="text-lg font-bold text-white">How this app is built</h2>
          <p class="mt-1 text-xs leading-relaxed text-indigo-100">${INTRO}</p>
        </div>
        <button id="tech-stack-close" type="button" aria-label="Close"
          class="shrink-0 rounded-md p-1 text-indigo-100 transition-colors hover:bg-white/20 hover:text-white">
          <span aria-hidden="true" class="text-lg leading-none">&times;</span>
        </button>
      </div>
      <div class="overflow-y-auto px-6 py-5">
        ${renderSections()}
      </div>
    </div>`;

  const open = () => {
    overlay.classList.remove("hidden");
    overlay.classList.add("flex");
  };
  const close = () => {
    overlay.classList.add("hidden");
    overlay.classList.remove("flex");
  };

  btn.addEventListener("click", open);
  overlay.addEventListener("click", (e) => {
    if (e.target === overlay) close(); // click on backdrop only
  });
  overlay.querySelector("#tech-stack-close")?.addEventListener("click", close);
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && !overlay.classList.contains("hidden")) close();
  });

  document.body.appendChild(btn);
  document.body.appendChild(overlay);
}


