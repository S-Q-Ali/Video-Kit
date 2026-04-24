# Workspace

## Replit Setup

- **Node.js module**: nodejs-24
- **Python module**: python-3.11 (venv at `VidLab-Platform/.venv/`)
- **Database**: PostgreSQL (Replit built-in, DATABASE_URL auto-set)
- **Backend workflow** (`Start application`): runs Flask app on port **8000** via `cd VidLab-Platform/backend && PORT=8000 ../.venv/bin/python main.py`
- **Web workflow** (`VidLab-Platform/artifacts/vidlab: web`): runs the React/Vite frontend on port **5000** (the artifact preview port). It proxies `/api` and `/analyzer-ui` to the Flask backend in dev (see `frontend/vite.config.ts`). Workflow name is preserved by the artifact platform; the source code lives in `VidLab-Platform/frontend/`.
- **API workflow** (`API Server`): runs Express API on port 3000 via `cd VidLab-Platform && PORT=3000 pnpm --filter @workspace/api-server run dev`
- **System deps**: ffmpeg, git, wget (from replit.nix)
- **Python deps**: flask==3.0.3, flask-cors==4.0.1, flask-limiter==3.8.0, yt-dlp, torch, transformers, Pillow, accelerate (installed in `.venv`)

## VidLab Flask App (backend/main.py)

The main user-facing app. Serves its own HTML template at `backend/templates/index.html`.

### Routes
- `GET /` — Main UI (HTML template)
- `POST /upload` — Upload video (max 200MB)
- `POST /analyze` — SSE: video metadata analysis via ffprobe
- `POST /duplicate` — SSE: strip metadata + extract frames + ZIP
- `POST /modify` — SSE: trim/resize/rotate/speed/mute/extract-audio via FFmpeg
- `POST /analyze-scenes` — SSE: AI scene captioning via BLIP model (lazy-loaded, ~450MB)
- `GET /download/<file_id>` — Download processed files
- `GET /frame/<dir_id>/<frame>` — Serve duplicate frame thumbnails
- `GET /scene-frame/<dir_id>/<frame>` — Serve scene analysis frame thumbnails

### YouTube Downloader (`backend/youtube_api.py`)
Mounted as a Blueprint in `main.py`. Uses `yt-dlp` and is rate-limited to 30 req/min/IP via `flask-limiter`. CORS is enabled (`flask-cors`) and the allowed origins are read from the `ALLOWED_ORIGINS` env var (comma-separated). When `ALLOWED_ORIGINS` is unset, all origins are allowed for local dev.

- `GET /api/video/health` — health probe
- `POST /api/video/info` — body `{ "youtube_url": "..." }`. Returns `{ title, thumbnail, duration, duration_seconds, channel, view_count, upload_date, webpage_url, available_formats: [{id,label,height},...] }`. Errors mapped to HTTP 400/403/404/410/504 with `{ error: "..." }`.
- `POST /api/video/download` — body `{ "youtube_url": "...", "quality": "highest"|"lowest"|"144p"|...|"2160p" }`. Streams the muxed MP4 back with `Content-Disposition: attachment`.

### Free-Tier Safety
- Background cleanup thread: deletes /tmp/vidlab_* files older than 1 hour, runs every 30 min
- Pre-process cleanup before each FFmpeg operation
- Max 3000 frames for duplicate extraction
- Max 50 frames for scene analysis (protects RAM)
- TimeoutExpired and disk quota errors return friendly JSON
- yt-dlp downloads stream to a temp dir that is wiped after the response is flushed

## VidLab React Frontend (`frontend/`)

React 18 + Vite + Tailwind + shadcn UI + wouter + TanStack Query. Built to be deployed standalone on Vercel; the dev server runs on Replit and proxies API calls to the Flask backend.

### Pages
- `/` — Home (marketing + tool tiles)
- `/analyzer` — Video Analyzer (iframes the existing Flask UI via `/analyzer-ui` proxy or `VITE_API_BASE_URL/`)
- `/youtube` — YouTube Downloader (uses `/api/video/info` and `/api/video/download`)

### Key files
- `src/lib/api.ts` — API client. Reads `VITE_API_BASE_URL`. Includes `fetchVideoInfo`, `downloadVideo` (XHR with progress), `triggerDownload`.
- `src/components/Layout.tsx` — Top + mobile nav.
- `src/components/youtube/*` — `DownloaderForm`, `VideoCard`, `QualitySelector`, `ProgressBar`, `LoadingSpinner`, `ErrorMessage`.
- `vite.config.ts` — dev proxy: `/api` and `/analyzer-ui` → `http://localhost:8000` (override with `VITE_DEV_API_PROXY`).
- `vercel.json` — Vercel build config (build via pnpm filter, SPA rewrites).
- `.env.example` — documents `VITE_API_BASE_URL` and `VITE_DEV_API_PROXY`.

### Hybrid deployment
- **Frontend** → Vercel. Set `VITE_API_BASE_URL` to the public Flask URL on Vercel. With `VITE_API_BASE_URL` set, the client calls the backend cross-origin (CORS must whitelist the Vercel domain via `ALLOWED_ORIGINS`).
- **Backend** → Replit Deployments. Set `ALLOWED_ORIGINS` to a comma-separated list of Vercel origins. The Flask app must be reachable on its public URL; expose port 8000 in `.replit` or deploy on its own port.

## Overview

pnpm workspace monorepo using TypeScript. Each package manages its own dependencies.

## Stack

- **Monorepo tool**: pnpm workspaces
- **Node.js version**: 24
- **Package manager**: pnpm
- **TypeScript version**: 5.9
- **API framework**: Express 5
- **Database**: PostgreSQL + Drizzle ORM
- **Validation**: Zod (`zod/v4`), `drizzle-zod`
- **API codegen**: Orval (from OpenAPI spec)
- **Build**: esbuild (CJS bundle)

## Structure

```text
artifacts-monorepo/
├── artifacts/              # Deployable applications
│   ├── api-server/         # Express API server
│   └── mockup-sandbox/     # Component preview sandbox
├── backend/                # VidLab Python/Flask backend + HTML frontend (formerly vidlab/)
│   ├── main.py             # Flask app with all routes (upload, analyze, duplicate, modify, download, frame)
│   ├── youtube_api.py      # YouTube downloader Blueprint (yt-dlp)
│   └── templates/
│       └── index.html      # Single-page vanilla JS frontend
├── frontend/               # VidLab React/Vite frontend (formerly artifacts/vidlab/)
│   └── src/                # React app — package name is still @workspace/vidlab
├── lib/                    # Shared libraries
│   ├── api-spec/           # OpenAPI spec + Orval codegen config
│   ├── api-client-react/   # Generated React Query hooks
│   ├── api-zod/            # Generated Zod schemas from OpenAPI
│   └── db/                 # Drizzle ORM schema + DB connection
├── scripts/                # Utility scripts (single workspace package)
│   └── src/                # Individual .ts scripts, run via `pnpm --filter @workspace/scripts run <script>`
├── pnpm-workspace.yaml     # pnpm workspace (frontend, artifacts/*, lib/*, lib/integrations/*, scripts)
├── tsconfig.base.json      # Shared TS options (composite, bundler resolution, es2022)
├── tsconfig.json           # Root TS project references
└── package.json            # Root package with hoisted devDeps
```

## TypeScript & Composite Projects

Every package extends `tsconfig.base.json` which sets `composite: true`. The root `tsconfig.json` lists all packages as project references. This means:

- **Always typecheck from the root** — run `pnpm run typecheck` (which runs `tsc --build --emitDeclarationOnly`). This builds the full dependency graph so that cross-package imports resolve correctly. Running `tsc` inside a single package will fail if its dependencies haven't been built yet.
- **`emitDeclarationOnly`** — we only emit `.d.ts` files during typecheck; actual JS bundling is handled by esbuild/tsx/vite...etc, not `tsc`.
- **Project references** — when package A depends on package B, A's `tsconfig.json` must list B in its `references` array. `tsc --build` uses this to determine build order and skip up-to-date packages.

## Root Scripts

- `pnpm run build` — runs `typecheck` first, then recursively runs `build` in all packages that define it
- `pnpm run typecheck` — runs `tsc --build --emitDeclarationOnly` using project references

## Packages

### `artifacts/api-server` (`@workspace/api-server`)

Express 5 API server. Routes live in `src/routes/` and use `@workspace/api-zod` for request and response validation and `@workspace/db` for persistence.

- Entry: `src/index.ts` — reads `PORT`, starts Express
- App setup: `src/app.ts` — mounts CORS, JSON/urlencoded parsing, routes at `/api`
- Routes: `src/routes/index.ts` mounts sub-routers; `src/routes/health.ts` exposes `GET /health` (full path: `/api/health`)
- Depends on: `@workspace/db`, `@workspace/api-zod`
- `pnpm --filter @workspace/api-server run dev` — run the dev server
- `pnpm --filter @workspace/api-server run build` — production esbuild bundle (`dist/index.cjs`)
- Build bundles an allowlist of deps (express, cors, pg, drizzle-orm, zod, etc.) and externalizes the rest

### `lib/db` (`@workspace/db`)

Database layer using Drizzle ORM with PostgreSQL. Exports a Drizzle client instance and schema models.

- `src/index.ts` — creates a `Pool` + Drizzle instance, exports schema
- `src/schema/index.ts` — barrel re-export of all models
- `src/schema/<modelname>.ts` — table definitions with `drizzle-zod` insert schemas (no models definitions exist right now)
- `drizzle.config.ts` — Drizzle Kit config (requires `DATABASE_URL`, automatically provided by Replit)
- Exports: `.` (pool, db, schema), `./schema` (schema only)

Production migrations are handled by Replit when publishing. In development, we just use `pnpm --filter @workspace/db run push`, and we fallback to `pnpm --filter @workspace/db run push-force`.

### `lib/api-spec` (`@workspace/api-spec`)

Owns the OpenAPI 3.1 spec (`openapi.yaml`) and the Orval config (`orval.config.ts`). Running codegen produces output into two sibling packages:

1. `lib/api-client-react/src/generated/` — React Query hooks + fetch client
2. `lib/api-zod/src/generated/` — Zod schemas

Run codegen: `pnpm --filter @workspace/api-spec run codegen`

### `lib/api-zod` (`@workspace/api-zod`)

Generated Zod schemas from the OpenAPI spec (e.g. `HealthCheckResponse`). Used by `api-server` for response validation.

### `lib/api-client-react` (`@workspace/api-client-react`)

Generated React Query hooks and fetch client from the OpenAPI spec (e.g. `useHealthCheck`, `healthCheck`).

### `scripts` (`@workspace/scripts`)

Utility scripts package. Each script is a `.ts` file in `src/` with a corresponding npm script in `package.json`. Run scripts via `pnpm --filter @workspace/scripts run <script>`. Scripts can import any workspace package (e.g., `@workspace/db`) by adding it as a dependency in `scripts/package.json`.
