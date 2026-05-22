import { ExternalLink } from "lucide-react";
import { Button } from "@/components/ui/button";
import { API_BASE_URL } from "@/lib/api";

/**
 * Video Analyzer page — embeds the legacy Flask analyzer UI in an iframe.
 *
 * In production (VITE_API_BASE_URL set), the iframe points directly to the
 * backend. In local dev, it goes through the Vite proxy /analyzer-ui → /.
 */
export default function VideoAnalyzerPage() {
  const analyzerUrl = API_BASE_URL ? `${API_BASE_URL}/` : "/analyzer-ui/";

  return (
    <div className="space-y-6">
      <header className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-3xl font-bold tracking-tight sm:text-4xl">
            Video Analyzer
          </h1>
          <p className="mt-2 max-w-2xl text-sm text-muted-foreground sm:text-base">
            Upload a video to inspect its metadata, modify it with FFmpeg, or
            extract its frames. The analyzer runs on the backend.
          </p>
        </div>
        <Button asChild variant="outline" data-testid="button-open-new-tab">
          <a href={analyzerUrl} target="_blank" rel="noreferrer">
            Open in new tab
            <ExternalLink className="ml-2 h-4 w-4" />
          </a>
        </Button>
      </header>

      <div className="overflow-hidden rounded-2xl border border-card-border bg-card shadow-sm">
        <iframe
          src={analyzerUrl}
          title="VidLab Video Analyzer"
          data-testid="iframe-analyzer"
          className="h-[80vh] min-h-[600px] w-full border-0 bg-background"
          loading="lazy"
        />
      </div>
    </div>
  );
}
