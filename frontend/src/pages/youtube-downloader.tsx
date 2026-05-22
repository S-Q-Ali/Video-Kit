import { useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { Download, RotateCcw } from "lucide-react";
import { Button } from "@/components/ui/button";
import { DownloaderForm } from "@/components/youtube/DownloaderForm";
import { VideoCard } from "@/components/youtube/VideoCard";
import { QualitySelector } from "@/components/youtube/QualitySelector";
import { ProgressBar, formatBytes } from "@/components/youtube/ProgressBar";
import { ErrorMessage } from "@/components/youtube/ErrorMessage";
import { LoadingSpinner } from "@/components/youtube/LoadingSpinner";
import {
  ApiError,
  downloadVideo,
  fetchVideoInfo,
  triggerDownload,
  type DownloadProgress,
  type VideoInfo,
} from "@/lib/api";

type DownloadState =
  | { status: "idle" }
  | { status: "downloading"; progress: DownloadProgress }
  | { status: "done"; filename: string; size: number }
  | { status: "error"; message: string };

export default function YouTubeDownloaderPage() {
  const [info, setInfo] = useState<VideoInfo | null>(null);
  const [submittedUrl, setSubmittedUrl] = useState<string>("");
  const [quality, setQuality] = useState<string>("highest");
  const [downloadState, setDownloadState] = useState<DownloadState>({ status: "idle" });

  const infoMutation = useMutation({
    mutationFn: (url: string) => fetchVideoInfo(url),
    onSuccess: (data, url) => {
      setInfo(data);
      setSubmittedUrl(url);
      setQuality("highest");
      setDownloadState({ status: "idle" });
    },
    onError: () => {
      setInfo(null);
    },
  });

  function handleFetch(url: string) {
    setDownloadState({ status: "idle" });
    infoMutation.mutate(url);
  }

  async function handleDownload() {
    if (!submittedUrl || !quality) return;
    setDownloadState({
      status: "downloading",
      progress: { loaded: 0, total: null, percent: null },
    });
    try {
      const result = await downloadVideo(submittedUrl, quality, (progress) => {
        setDownloadState({ status: "downloading", progress });
      });
      triggerDownload(result.blob, result.filename);
      setDownloadState({
        status: "done",
        filename: result.filename,
        size: result.blob.size,
      });
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Download failed.";
      setDownloadState({ status: "error", message });
    }
  }

  function reset() {
    setInfo(null);
    setSubmittedUrl("");
    setDownloadState({ status: "idle" });
    infoMutation.reset();
  }

  const fetchError = infoMutation.error
    ? infoMutation.error instanceof ApiError
      ? infoMutation.error.message
      : "Could not fetch video info."
    : null;

  return (
    <div className="space-y-8">
      <header className="space-y-2">
        <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
          YouTube Downloader
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground sm:text-base">
          Paste a YouTube URL, choose a quality, and download. We pick the right
          format automatically.
        </p>
      </header>

      <section className="rounded-2xl border border-card-border bg-card p-5 shadow-sm sm:p-6">
        <DownloaderForm
          onSubmit={handleFetch}
          isLoading={infoMutation.isPending}
        />
        {fetchError ? (
          <div className="mt-4">
            <ErrorMessage message={fetchError} testId="error-fetch" />
          </div>
        ) : null}
      </section>

      {infoMutation.isPending ? (
        <LoadingSpinner label="Fetching video info..." className="py-10" />
      ) : null}

      {info ? (
        <section className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
          <VideoCard info={info} />

          <aside className="space-y-5 rounded-2xl border border-card-border bg-card p-5 shadow-sm sm:p-6">
            <div>
              <h3 className="text-sm font-semibold uppercase tracking-wide text-muted-foreground">
                Download
              </h3>
              <p className="mt-1 text-xs text-muted-foreground">
                Choose your preferred quality.
              </p>
            </div>

            <QualitySelector
              qualities={info.available_formats}
              value={quality}
              onChange={setQuality}
              disabled={downloadState.status === "downloading"}
            />

            <Button
              type="button"
              size="lg"
              className="w-full"
              onClick={handleDownload}
              disabled={downloadState.status === "downloading" || !info.available_formats.length}
              data-testid="button-download"
            >
              {downloadState.status === "downloading" ? (
                <LoadingSpinner size="sm" />
              ) : (
                <>
                  <Download className="mr-2 h-4 w-4" />
                  Download
                </>
              )}
            </Button>

            {downloadState.status === "downloading" ? (
              <div className="space-y-2">
                <ProgressBar
                  percent={downloadState.progress.percent}
                  label={
                    downloadState.progress.percent != null
                      ? "Downloading..."
                      : "Preparing on server..."
                  }
                />
                <p
                  className="text-center text-xs text-muted-foreground"
                  data-testid="text-bytes-progress"
                >
                  {downloadState.progress.total
                    ? `${formatBytes(downloadState.progress.loaded)} of ${formatBytes(
                        downloadState.progress.total,
                      )}`
                    : downloadState.progress.loaded > 0
                      ? formatBytes(downloadState.progress.loaded)
                      : "Waiting for first byte..."}
                </p>
              </div>
            ) : null}

            {downloadState.status === "done" ? (
              <div
                className="rounded-lg border border-emerald-500/30 bg-emerald-500/10 p-3 text-sm text-emerald-700 dark:text-emerald-300"
                data-testid="status-download-done"
              >
                Saved <span className="font-medium">{downloadState.filename}</span> ·{" "}
                {formatBytes(downloadState.size)}
              </div>
            ) : null}

            {downloadState.status === "error" ? (
              <ErrorMessage
                message={downloadState.message}
                testId="error-download"
              />
            ) : null}

            <Button
              type="button"
              variant="ghost"
              onClick={reset}
              className="w-full"
              data-testid="button-reset"
            >
              <RotateCcw className="mr-2 h-4 w-4" />
              Start over
            </Button>
          </aside>
        </section>
      ) : null}
    </div>
  );
}
