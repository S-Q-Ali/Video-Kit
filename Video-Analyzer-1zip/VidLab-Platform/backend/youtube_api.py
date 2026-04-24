"""
YouTube downloader API.

Exposes a Flask Blueprint with three endpoints:
  GET  /api/video/health   - service health probe (also reports ffmpeg)
  POST /api/video/info     - extract metadata + available formats
  POST /api/video/download - stream a downloaded video back to the client

Backed by yt-dlp + ffmpeg. ffmpeg is required to merge separate video and
audio streams (which YouTube uses for everything 1080p and above, including
1440p and 2160p / 4K).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
import threading
import time
import uuid
from typing import Any

from flask import Blueprint, after_this_request, jsonify, request, send_file
from yt_dlp import YoutubeDL
from yt_dlp.utils import (
    DownloadError,
    ExtractorError,
    GeoRestrictedError,
    UnavailableVideoError,
)

youtube_bp = Blueprint("youtube", __name__, url_prefix="/api/video")

# Per-process download root. Lives next to the Flask app so it is easy to
# inspect, and is wiped per-request after the response is delivered.
DOWNLOAD_DIR = os.environ.get(
    "VIDLAB_DOWNLOAD_DIR",
    os.path.join(os.path.dirname(os.path.abspath(__file__)), "downloads"),
)
os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Hard cap for any single download to protect the free-tier disk + memory.
DOWNLOAD_TIMEOUT_SECONDS = int(os.environ.get("VIDLAB_DOWNLOAD_TIMEOUT", "600"))  # 10 min
SOCKET_TIMEOUT = 30
RETRIES = 2

# Quality presets. Every entry uses `bestvideo+bestaudio` so 1080p+ (which
# YouTube serves as separate adaptive streams) gets merged by ffmpeg into a
# single MP4. The trailing fallback (`/best[height<=N]`) covers the rare case
# where YouTube only has a pre-muxed format at that resolution.
QUALITY_PRESETS: dict[str, str] = {
    "lowest":  "worstvideo*+worstaudio/worst",
    "highest": "bestvideo*+bestaudio/best",
    "144p":  "bestvideo[height<=144]+bestaudio/best[height<=144]",
    "240p":  "bestvideo[height<=240]+bestaudio/best[height<=240]",
    "360p":  "bestvideo[height<=360]+bestaudio/best[height<=360]",
    "480p":  "bestvideo[height<=480]+bestaudio/best[height<=480]",
    "720p":  "bestvideo[height<=720]+bestaudio/best[height<=720]",
    "1080p": "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
    "1440p": "bestvideo[height<=1440]+bestaudio/best[height<=1440]",
    "2160p": "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
    "4k":    "bestvideo[height<=2160]+bestaudio/best[height<=2160]",
}

YOUTUBE_URL_RE = re.compile(
    r"^(https?://)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)/.+",
    re.IGNORECASE,
)


# ----------------------------------------------------------------------------
# ffmpeg detection
# ----------------------------------------------------------------------------

def _ffmpeg_path() -> str | None:
    """Return the absolute path to ffmpeg, or None if not on PATH."""
    return shutil.which("ffmpeg")


def _ffmpeg_version() -> str | None:
    p = _ffmpeg_path()
    if not p:
        return None
    try:
        out = subprocess.run(
            [p, "-version"], capture_output=True, text=True, timeout=5, check=False
        )
        first = (out.stdout or "").splitlines()[0] if out.stdout else ""
        return first or None
    except Exception:  # noqa: BLE001
        return None


# ----------------------------------------------------------------------------
# Validation + error helpers
# ----------------------------------------------------------------------------

def _is_valid_youtube_url(url: str) -> bool:
    if not url or not isinstance(url, str) or len(url) > 2048:
        return False
    return bool(YOUTUBE_URL_RE.match(url.strip()))


def _classify_error(exc: Exception) -> tuple[str, int]:
    msg = str(exc).lower()

    if "ffmpeg" in msg and ("not found" in msg or "could not" in msg or "missing" in msg):
        return ("FFmpeg is required for high-resolution downloads but is not installed on the server.", 500)
    if "no space left" in msg or "disk" in msg and "full" in msg:
        return ("The server is out of disk space. Please try again later.", 507)
    if isinstance(exc, GeoRestrictedError) or "geo" in msg:
        return ("This video is geo-restricted and cannot be downloaded from this server.", 403)
    if isinstance(exc, UnavailableVideoError) or "video unavailable" in msg or "not available" in msg:
        return ("This video is unavailable. It may have been removed or set to private.", 404)
    if "private" in msg:
        return ("This video is private and cannot be downloaded.", 403)
    if "age" in msg and ("restrict" in msg or "confirm" in msg or "sign in" in msg):
        return ("This video is age-restricted and cannot be downloaded without authentication.", 403)
    if "members" in msg or "premium" in msg or "subscriber" in msg:
        return ("This video is restricted to members or premium subscribers.", 403)
    if "copyright" in msg:
        return ("This video is unavailable due to copyright restrictions.", 451)
    if "live" in msg and "stream" in msg:
        return ("Live streams cannot be downloaded.", 400)
    if "timeout" in msg or "timed out" in msg:
        return ("The request timed out. Please try again or pick a lower quality.", 504)
    if "http error 4" in msg or "404" in msg:
        return ("Video not found.", 404)
    if "requested format is not available" in msg or "no video formats found" in msg:
        return ("That quality is not available for this video. Please pick a different quality.", 400)
    if isinstance(exc, (DownloadError, ExtractorError)):
        return ("Could not process this video. It may be unavailable or unsupported.", 502)
    return ("Failed to process this video.", 500)


def _extract_formats(info: dict[str, Any]) -> list[dict[str, Any]]:
    raw_formats = info.get("formats") or []
    heights: set[int] = set()
    for f in raw_formats:
        h = f.get("height")
        if isinstance(h, int) and h > 0:
            heights.add(h)

    standard = [144, 240, 360, 480, 720, 1080, 1440, 2160]
    available_standard = sorted({h for h in standard if any(rh >= h for rh in heights)})

    qualities: list[dict[str, Any]] = [
        {"id": "highest", "label": "Highest", "height": max(heights) if heights else None},
        {"id": "lowest",  "label": "Lowest",  "height": min(heights) if heights else None},
    ]
    for h in available_standard:
        label = f"{h}p" + (" (4K)" if h == 2160 else " (2K)" if h == 1440 else "")
        qualities.append({"id": f"{h}p", "label": label, "height": h})

    return qualities


def _safe_filename(title: str, max_len: int = 80) -> str:
    cleaned = re.sub(r"[^\w\s.-]", "", title or "video").strip()
    cleaned = re.sub(r"\s+", "_", cleaned)
    return (cleaned or "video")[:max_len]


# ----------------------------------------------------------------------------
# Endpoints
# ----------------------------------------------------------------------------

@youtube_bp.route("/health", methods=["GET"])
def health():
    fp = _ffmpeg_path()
    return jsonify({
        "status": "ok",
        "service": "youtube-downloader",
        "ffmpeg_available": fp is not None,
        "ffmpeg_path": fp,
        "ffmpeg_version": _ffmpeg_version(),
        "download_dir": DOWNLOAD_DIR,
        "download_timeout_seconds": DOWNLOAD_TIMEOUT_SECONDS,
    })


@youtube_bp.route("/info", methods=["POST"])
def video_info():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("youtube_url") or "").strip()

    if not _is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL."}), 400

    ydl_opts = {
        "quiet": True,
        "no_warnings": True,
        "skip_download": True,
        "nocheckcertificate": True,
        "socket_timeout": 20,
        "extract_flat": False,
    }

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
    except Exception as exc:  # noqa: BLE001
        message, status = _classify_error(exc)
        return jsonify({"error": message}), status

    if info is None:
        return jsonify({"error": "Could not extract video information."}), 502
    if info.get("is_live"):
        return jsonify({"error": "Live streams cannot be downloaded."}), 400

    duration = info.get("duration")
    duration_str = None
    if isinstance(duration, (int, float)) and duration > 0:
        total = int(duration)
        h, rem = divmod(total, 3600)
        m, s = divmod(rem, 60)
        duration_str = f"{h:d}:{m:02d}:{s:02d}" if h else f"{m:d}:{s:02d}"

    return jsonify({
        "title":     info.get("title") or "Untitled",
        "thumbnail": info.get("thumbnail"),
        "duration_seconds": duration if isinstance(duration, (int, float)) else None,
        "duration":  duration_str,
        "channel":   info.get("uploader") or info.get("channel"),
        "view_count": info.get("view_count"),
        "upload_date": info.get("upload_date"),
        "webpage_url": info.get("webpage_url"),
        "available_formats": _extract_formats(info),
    })


@youtube_bp.route("/download", methods=["POST"])
def video_download():
    payload = request.get_json(silent=True) or {}
    url = (payload.get("youtube_url") or "").strip()
    quality = (payload.get("quality") or "highest").strip().lower()

    if not _is_valid_youtube_url(url):
        return jsonify({"error": "Invalid YouTube URL."}), 400

    if quality not in QUALITY_PRESETS:
        return jsonify({
            "error": "Invalid quality.",
            "valid_qualities": sorted(QUALITY_PRESETS.keys()),
        }), 400

    # ffmpeg is required to merge separate video + audio streams (1080p, 1440p,
    # 2160p / 4K). For "lowest" / pre-muxed formats we *might* get away without
    # it, but we require it unconditionally so quality is consistent.
    needs_merge = quality not in {"lowest"}
    ffmpeg = _ffmpeg_path()
    if needs_merge and not ffmpeg:
        return jsonify({
            "error": "FFmpeg is required for 4K downloads but is not installed on the server.",
        }), 500

    # Per-request temp dir so we can wipe it cleanly even on partial failures.
    job_dir = tempfile.mkdtemp(prefix=f"vidlab_yt_{uuid.uuid4().hex}_", dir=DOWNLOAD_DIR)
    out_template = os.path.join(job_dir, "%(title).80s.%(ext)s")

    ydl_opts: dict[str, Any] = {
        "quiet": True,
        "no_warnings": True,
        "format": QUALITY_PRESETS[quality],
        "outtmpl": out_template,
        "merge_output_format": "mp4",
        "noplaylist": True,
        "nocheckcertificate": True,
        "socket_timeout": SOCKET_TIMEOUT,
        "concurrent_fragment_downloads": 4,
        "retries": RETRIES,
        "fragment_retries": RETRIES,
        # Force the final file to be MP4, re-encoding only if absolutely required.
        "postprocessors": [
            {"key": "FFmpegVideoConvertor", "preferedformat": "mp4"},
        ],
    }
    if ffmpeg:
        ydl_opts["ffmpeg_location"] = ffmpeg

    info_dict: dict[str, Any] | None = None
    downloaded_path: str | None = None
    deadline = time.monotonic() + DOWNLOAD_TIMEOUT_SECONDS

    def _progress_hook(d: dict[str, Any]) -> None:
        if time.monotonic() > deadline:
            raise TimeoutError("Download exceeded the per-request time limit.")

    ydl_opts["progress_hooks"] = [_progress_hook]

    def _cleanup_dir() -> None:
        shutil.rmtree(job_dir, ignore_errors=True)

    try:
        with YoutubeDL(ydl_opts) as ydl:
            info_dict = ydl.extract_info(url, download=True)
            if info_dict is None:
                raise RuntimeError("yt-dlp returned no info")
            base = ydl.prepare_filename(info_dict)
            stem, _ = os.path.splitext(base)
            # After merge yt-dlp produces .mp4; some fallbacks land as .mkv / .webm.
            for candidate in (f"{stem}.mp4", base, f"{stem}.mkv", f"{stem}.webm"):
                if candidate and os.path.exists(candidate):
                    downloaded_path = candidate
                    break
    except TimeoutError as exc:
        _cleanup_dir()
        return jsonify({"error": str(exc)}), 504
    except Exception as exc:  # noqa: BLE001
        _cleanup_dir()
        message, status = _classify_error(exc)
        return jsonify({"error": message}), status

    if not downloaded_path or not os.path.exists(downloaded_path):
        _cleanup_dir()
        return jsonify({"error": "Download failed: output file missing."}), 500

    title = (info_dict or {}).get("title") or "video"
    ext = os.path.splitext(downloaded_path)[1].lstrip(".") or "mp4"
    download_name = f"{_safe_filename(title)}.{ext}"

    captured_dir = job_dir  # for the closure

    @after_this_request
    def _schedule_cleanup(response):  # type: ignore[no-untyped-def]
        # Wipe the temp dir after the client has had time to finish reading.
        # Streaming with `send_file(conditional=True)` can keep the fd open;
        # delaying gives the OS a window to flush before unlink.
        def _delete_later():
            time.sleep(60)
            shutil.rmtree(captured_dir, ignore_errors=True)
        threading.Thread(target=_delete_later, daemon=True).start()
        return response

    mimetype = "video/mp4" if ext == "mp4" else f"video/{ext}"
    # send_file streams the file in chunks (does NOT load it into memory).
    return send_file(
        downloaded_path,
        mimetype=mimetype,
        as_attachment=True,
        download_name=download_name,
        conditional=True,
    )
