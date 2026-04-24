# VidLab — Web Frontend

React 18 + Vite + Tailwind + shadcn UI. This package is the user-facing site:

- `/` — Home
- `/analyzer` — Video Analyzer (iframes the Flask UI)
- `/youtube` — YouTube Downloader (calls the Flask API)

It is designed for **hybrid deployment**: the frontend deploys to Vercel and the Flask backend stays on Replit (or wherever you host it).

## Local development

The whole monorepo runs from the project root:

```bash
pnpm install
```

Then start the two workflows on Replit (already configured):

- `Start application` — Flask backend on port **8000**
- `VidLab-Platform/artifacts/vidlab: web` — Vite dev server on port **5000** (workflow name kept by the artifact platform; the source now lives in `VidLab-Platform/frontend/`)

In dev, Vite proxies `/api/*` and `/analyzer-ui/*` to `http://localhost:8000`, so you can leave `VITE_API_BASE_URL` empty.

To override the proxy target locally:

```bash
VITE_DEV_API_PROXY=http://127.0.0.1:9000 pnpm --filter @workspace/vidlab run dev
```

## Environment variables

See `.env.example`.

| Variable | When | Purpose |
|---|---|---|
| `VITE_API_BASE_URL` | Build time (Vercel) | Public URL of the Flask backend, e.g. `https://vidlab-backend.example.com`. Leave empty in local dev. |
| `VITE_DEV_API_PROXY` | Local dev only | Override the Vite dev proxy target. Defaults to `http://localhost:8000`. |

## Deploying the frontend to Vercel

1. Push the repo to GitHub.
2. In Vercel, **Import Project** from the GitHub repo.
3. Set the **Root Directory** to `VidLab-Platform/frontend`. (Vercel automatically picks up `vercel.json`, which uses pnpm filters from the monorepo root.)
4. Add a **Project Environment Variable**:
   - `VITE_API_BASE_URL` = `https://<your-flask-backend>.replit.app` (no trailing slash)
5. Deploy.

`vercel.json` configures:
- `installCommand: pnpm install --frozen-lockfile`
- `buildCommand: pnpm --filter @workspace/vidlab run build`
- `outputDirectory: dist/public`
- A SPA rewrite so all routes serve `index.html`.

## Deploying the backend on Replit

The Flask backend serves both the legacy analyzer UI (at `/`) and the new JSON API at `/api/video/*`. To allow your Vercel frontend to call it:

1. In the backend environment, set:
   ```
   ALLOWED_ORIGINS=https://<your-vercel-app>.vercel.app,https://<your-custom-domain>
   ```
   (comma-separated; leave unset only for fully open dev.)
2. Make sure the deployment exposes port **8000** publicly.
3. Test:
   ```bash
   curl -i https://<backend>/api/video/health
   ```

## Project layout

```
src/
├── App.tsx                   # router (wouter) + providers
├── lib/
│   └── api.ts                # API client (info, download, progress)
├── components/
│   ├── Layout.tsx            # top + mobile nav
│   └── youtube/
│       ├── DownloaderForm.tsx
│       ├── VideoCard.tsx
│       ├── QualitySelector.tsx
│       ├── ProgressBar.tsx
│       ├── LoadingSpinner.tsx
│       └── ErrorMessage.tsx
└── pages/
    ├── home.tsx
    ├── video-analyzer.tsx    # iframes the Flask UI
    └── youtube-downloader.tsx
```

## Scripts

```bash
pnpm --filter @workspace/vidlab run dev      # Vite dev server
pnpm --filter @workspace/vidlab run build    # Production build → dist/public
pnpm --filter @workspace/vidlab run preview  # Preview the production build
```
