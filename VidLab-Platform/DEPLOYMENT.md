# VidLab Deployment Split

This repo is now organized for separate deployments:

- Frontend: `VidLab-Platform/frontend` (React + Vite, static output)
- Backend: `VidLab-Platform/backend` (Flask API + analyzer UI)

## Frontend (Vercel)

1. In Vercel, import your GitHub repo.
2. Set **Root Directory** to `VidLab-Platform/frontend`.
3. Add environment variable:
   - `VITE_API_BASE_URL=https://<your-backend-domain>`
4. Deploy.

`frontend/vercel.json` already handles:
- Install from workspace root (`pnpm -C .. install --frozen-lockfile`)
- Build only frontend package (`pnpm -C .. --filter @workspace/vidlab run build`)
- Output directory (`dist/public`)
- SPA rewrite to `index.html`

## Backend (separate service)

Deploy `VidLab-Platform/backend` on your backend platform of choice (Render, Railway, Replit Deployments, VPS, etc.).

Required setup:

1. Install dependencies:
   - `pip install -r requirements.txt`
2. Configure environment variables (see `.env.example`):
   - `PORT=8000`
   - `ALLOWED_ORIGINS=https://<your-vercel-domain>`
3. Start server:
   - `python main.py`

Health check:

- `GET https://<your-backend-domain>/api/video/health`

## Important Notes

- Frontend and backend are decoupled at runtime through `VITE_API_BASE_URL`.
- CORS is enforced by backend `ALLOWED_ORIGINS`; include every frontend domain you use.
- In local development, frontend can still proxy `/api` to `http://localhost:8000`.
