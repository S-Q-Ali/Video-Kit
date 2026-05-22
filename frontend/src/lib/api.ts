/**
 * API client for the VidLab backend.
 *
 * Set VITE_API_BASE_URL at build time to point at the deployed Flask backend
 * (e.g. https://vidlab-backend.example.com). When unset (typical local dev),
 * we use a same-origin /api path which Vite proxies to the local Flask
 * server (see vite.config.ts).
 */

const RAW_BASE = (import.meta.env.VITE_API_BASE_URL ?? "").trim();

export const API_BASE_URL = RAW_BASE.replace(/\/$/, "");

export interface VideoFormat {
  id: string;
  label: string;
  height: number | null;
}

export interface VideoInfo {
  title: string;
  thumbnail: string | null;
  duration: string | null;
  duration_seconds: number | null;
  channel: string | null;
  view_count: number | null;
  upload_date: string | null;
  webpage_url: string | null;
  available_formats: VideoFormat[];
}

export class ApiError extends Error {
  status: number;
  constructor(message: string, status: number) {
    super(message);
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseError(res: Response): Promise<never> {
  let message = `Request failed (${res.status})`;
  try {
    const data = await res.json();
    if (data && typeof data.error === "string") message = data.error;
  } catch {
    // ignore JSON parse errors
  }
  throw new ApiError(message, res.status);
}

export async function fetchVideoInfo(youtubeUrl: string): Promise<VideoInfo> {
  const res = await fetch(`${API_BASE_URL}/api/video/info`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ youtube_url: youtubeUrl }),
  });
  if (!res.ok) await parseError(res);
  return res.json();
}

/**
 * Builds the URL the browser uses to download a video.
 * We POST and surface progress through XHR so the user gets a progress bar.
 */
export function downloadVideoUrl(): string {
  return `${API_BASE_URL}/api/video/download`;
}

export interface DownloadProgress {
  loaded: number;
  total: number | null;
  percent: number | null;
}

export interface DownloadResult {
  blob: Blob;
  filename: string;
}

/**
 * Performs a POST to /api/video/download and reports progress.
 * Returns a Blob and a suggested filename parsed from Content-Disposition.
 */
export function downloadVideo(
  youtubeUrl: string,
  quality: string,
  onProgress?: (progress: DownloadProgress) => void,
  signal?: AbortSignal,
): Promise<DownloadResult> {
  return new Promise<DownloadResult>((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", downloadVideoUrl(), true);
    xhr.responseType = "blob";
    xhr.setRequestHeader("Content-Type", "application/json");

    xhr.onprogress = (e) => {
      const total = e.lengthComputable ? e.total : null;
      const percent = total ? Math.min(100, Math.round((e.loaded / total) * 100)) : null;
      onProgress?.({ loaded: e.loaded, total, percent });
    };

    xhr.onerror = () => reject(new ApiError("Network error while downloading.", 0));
    xhr.ontimeout = () => reject(new ApiError("Download timed out.", 504));
    xhr.onabort = () => reject(new ApiError("Download cancelled.", 0));

    xhr.onload = async () => {
      if (xhr.status < 200 || xhr.status >= 300) {
        let message = `Download failed (${xhr.status})`;
        try {
          const text = await (xhr.response as Blob).text();
          const data = JSON.parse(text);
          if (data?.error) message = data.error;
        } catch {
          // ignore
        }
        reject(new ApiError(message, xhr.status));
        return;
      }

      const dispo = xhr.getResponseHeader("Content-Disposition") ?? "";
      const match = /filename\*?=(?:UTF-8'')?"?([^";]+)"?/i.exec(dispo);
      const filename = match ? decodeURIComponent(match[1]) : "video.mp4";
      resolve({ blob: xhr.response as Blob, filename });
    };

    if (signal) {
      signal.addEventListener("abort", () => xhr.abort(), { once: true });
    }

    xhr.send(JSON.stringify({ youtube_url: youtubeUrl, quality }));
  });
}

export function triggerDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  document.body.appendChild(a);
  a.click();
  a.remove();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
