# VidLab

A browser-based video analysis toolkit with AI-powered scene detection, transcription, and editing — all running on-device.

## Tech Stack

| Layer | Technology |
|-------|-----------|
| **Frontend** | React 19, TypeScript, Vite 7, Tailwind CSS 4, shadcn/ui |
| **Backend** | Python Flask 3, Gunicorn |
| **AI/ML** | OpenAI Whisper (transcription), BLIP-large (scene captioning), sentence-transformers |
| **Video** | FFmpeg / FFprobe (processing), yt-dlp (YouTube download) |
| **Monorepo** | pnpm workspaces |

## Project Structure

```
VidLab-Platform/
├── backend/                # Flask API + legacy analyzer UI
│   ├── main.py             # All routes and core processing
│   ├── youtube_api.py      # YouTube downloader blueprint
│   ├── templates/          # Jinja2 HTML templates
│   └── requirements.txt
├── frontend/               # React + Vite SPA
│   ├── src/                # Routes, components, pages
│   ├── vercel.json         # Vercel deployment config
│   └── README.md           # Frontend-specific setup
├── lib/
│   ├── api-spec/           # OpenAPI spec + Orval config
│   ├── api-client-react/   # Generated React Query hooks
│   ├── api-zod/            # Generated Zod schemas
│   └── db/                 # Drizzle ORM (PostgreSQL)
├── DEPLOYMENT.md           # Deployment guide
└── package.json            # Workspace root
```

## Quick Start

### Prerequisites
- Python 3.10+
- Node.js 20+
- FFmpeg (install via `choco install ffmpeg` or `apt install ffmpeg`)

### Backend

```bash
cd VidLab-Platform/backend
pip install -r requirements.txt
python main.py
```

The server starts on `http://localhost:8080` and serves both the legacy UI and JSON API.

### Frontend

```bash
# From the monorepo root (VidLab-Platform/)
pnpm install
pnpm --filter @workspace/vidlab run dev
```

## Features

- **Video Analysis** — metadata extraction (codec, resolution, bitrate, duration) via FFprobe
- **Scene Detection** — AI-powered scene segmentation using BLIP-large captions + semantic similarity
- **Transcription** — Speech-to-text via Whisper tiny; videos >5 min are automatically split into chunks
- **Video Editing** — Trim, resize, rotate, change speed, mute, extract audio (FFmpeg)
- **Frame Extraction** — Export frames at custom FPS, grouped by scene
- **YouTube Download** — Download videos/audio via yt-dlp with format selection

## Scripts

```bash
# Frontend
pnpm --filter @workspace/vidlab run dev     # Vite dev server
pnpm --filter @workspace/vidlab run build   # Production build
pnpm --filter @workspace/vidlab run serve   # Preview build

# Backend
python backend/main.py                       # Start Flask (port 8080)
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for separating frontend (Vercel) and backend (Render/Railway/Replit).
