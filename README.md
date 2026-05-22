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
- pnpm

### One-command start

```bash
# Windows
.\start.ps1

# Unix / macOS
chmod +x start.sh && ./start.sh
```

### Manual start

Terminal 1 — Backend (Flask):
```bash
cd backend
pip install -r requirements.txt
python main.py         # → http://localhost:8000
```

Terminal 2 — Frontend (Vite):
```bash
cd frontend
pnpm install
pnpm run dev           # → http://localhost:5173
```

## Features

- **Video Analysis** — metadata extraction (codec, resolution, bitrate, duration) via FFprobe
- **Scene Detection** — AI-powered scene segmentation using BLIP-large captions + semantic similarity
- **Transcription** — Speech-to-text via Whisper tiny; videos >5 min are automatically split into chunks
- **Video Editing** — Trim, resize, rotate, change speed, mute, extract audio (FFmpeg)
- **Frame Extraction** — Export frames at custom FPS, grouped by scene
- **YouTube Download** — Download videos/audio via yt-dlp with format selection

## API Routes

All analyzer and processing endpoints are available under both the legacy paths and the versioned `/api/v1/` prefix:

| Method | Legacy | Versioned | Purpose |
|--------|--------|-----------|---------|
| `GET` | `/` | — | Legacy Flask analyzer UI |
| `POST` | `/upload` | `/api/v1/upload` | Upload video |
| `POST` | `/analyze` | `/api/v1/analyze` | Metadata analysis |
| `POST` | `/duplicate` | `/api/v1/duplicate` | Clean copy + frame extract |
| `POST` | `/modify` | `/api/v1/modify` | Video modification |
| `GET` | `/download/<id>` | `/api/v1/download/<id>` | Download processed files |
| `GET` | `/frame/<dir>/<name>` | `/api/v1/frame/<dir>/<name>` | Serve frame JPEG |
| `POST` | `/analyze-scenes` | `/api/v1/analyze-scenes` | AI scene analysis |
| `GET` | `/scene-frame/<dir>/<name>` | `/api/v1/scene-frame/<dir>/<name>` | Scene thumbnail |
| `POST` | `/generate-transcript` | `/api/v1/generate-transcript` | Speech-to-text transcription |
| `GET` | `/download-transcript/<name>` | `/api/v1/download-transcript/<name>` | Download transcript |
| `POST` | — | `/api/video/info` | YouTube video info |
| `POST` | — | `/api/video/download` | YouTube video download |

## Environment Variables

### Backend (`backend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `PORT` | `8000` | Flask server port |
| `ALLOWED_ORIGINS` | localhost origins | Comma-separated CORS origins |

### Frontend (`frontend/.env`)

| Variable | Default | Description |
|----------|---------|-------------|
| `VITE_API_BASE_URL` | *(empty)* | Backend URL for production. Empty = same-origin (Vite proxy in dev) |
| `VITE_DEV_API_PROXY` | `http://localhost:8000` | Dev proxy target override |

## Scripts

```bash
# Frontend
pnpm --filter @workspace/vidlab run dev     # Vite dev server
pnpm --filter @workspace/vidlab run build   # Production build
pnpm --filter @workspace/vidlab run serve   # Preview build

# Backend
cd backend && python main.py                 # Start Flask (port 8000)
```

## Deployment

See [DEPLOYMENT.md](DEPLOYMENT.md) for separating frontend (Vercel) and backend (Render/Railway/Replit).
