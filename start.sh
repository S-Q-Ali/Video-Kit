#!/usr/bin/env bash
# Start both backend (Flask) and frontend (Vite) for local development.
# Run this from the project root.
set -e

echo "=== VidLab — Starting Backend (Flask) ==="
cd backend
python main.py &
BACKEND_PID=$!
cd ..

sleep 3

echo "=== VidLab — Starting Frontend (Vite) ==="
echo "Backend:  http://localhost:8000"
echo "Frontend: http://localhost:5173"

cleanup() {
    echo "Stopping backend..."
    kill "$BACKEND_PID" 2>/dev/null
    wait "$BACKEND_PID" 2>/dev/null
}
trap cleanup EXIT

cd frontend
pnpm run dev
