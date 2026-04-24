import { Clock, User, Eye, ExternalLink } from "lucide-react";
import type { VideoInfo } from "@/lib/api";

interface VideoCardProps {
  info: VideoInfo;
}

function formatViews(n: number | null | undefined): string | null {
  if (n == null) return null;
  if (n < 1000) return `${n} views`;
  if (n < 1_000_000) return `${(n / 1000).toFixed(1)}K views`;
  if (n < 1_000_000_000) return `${(n / 1_000_000).toFixed(1)}M views`;
  return `${(n / 1_000_000_000).toFixed(1)}B views`;
}

export function VideoCard({ info }: VideoCardProps) {
  const views = formatViews(info.view_count);
  return (
    <article
      className="overflow-hidden rounded-xl border border-card-border bg-card shadow-sm"
      data-testid="card-video-info"
    >
      {info.thumbnail ? (
        <div className="relative aspect-video w-full overflow-hidden bg-muted">
          <img
            src={info.thumbnail}
            alt={info.title}
            data-testid="img-thumbnail"
            className="h-full w-full object-cover"
            loading="lazy"
          />
          {info.duration ? (
            <span
              data-testid="text-duration-overlay"
              className="absolute bottom-3 right-3 rounded-md bg-black/80 px-2 py-1 font-mono text-xs font-medium text-white shadow"
            >
              {info.duration}
            </span>
          ) : null}
        </div>
      ) : null}
      <div className="space-y-3 p-5">
        <h3
          data-testid="text-video-title"
          className="line-clamp-2 text-lg font-semibold leading-snug text-foreground"
        >
          {info.title}
        </h3>
        <div className="flex flex-wrap items-center gap-x-4 gap-y-2 text-sm text-muted-foreground">
          {info.channel ? (
            <span
              className="flex items-center gap-1.5"
              data-testid="text-channel"
            >
              <User className="h-4 w-4" />
              {info.channel}
            </span>
          ) : null}
          {info.duration ? (
            <span
              className="flex items-center gap-1.5"
              data-testid="text-duration"
            >
              <Clock className="h-4 w-4" />
              {info.duration}
            </span>
          ) : null}
          {views ? (
            <span
              className="flex items-center gap-1.5"
              data-testid="text-views"
            >
              <Eye className="h-4 w-4" />
              {views}
            </span>
          ) : null}
          {info.webpage_url ? (
            <a
              href={info.webpage_url}
              target="_blank"
              rel="noreferrer"
              className="ml-auto flex items-center gap-1.5 text-primary hover:underline"
              data-testid="link-webpage"
            >
              Open <ExternalLink className="h-3.5 w-3.5" />
            </a>
          ) : null}
        </div>
      </div>
    </article>
  );
}
