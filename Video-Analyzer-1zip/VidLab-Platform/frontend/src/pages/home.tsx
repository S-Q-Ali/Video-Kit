import { Link } from "wouter";
import { ArrowRight, Film, Download, Zap, Shield, Sparkles } from "lucide-react";
import { Button } from "@/components/ui/button";

const FEATURES = [
  {
    icon: Zap,
    title: "Fast",
    desc: "FFmpeg-powered processing with streaming progress updates.",
  },
  {
    icon: Shield,
    title: "Private",
    desc: "Files are auto-deleted from the server after one hour.",
  },
  {
    icon: Sparkles,
    title: "Free",
    desc: "No sign-up, no API keys, no usage limits.",
  },
];

const TOOLS = [
  {
    to: "/analyzer",
    icon: Film,
    title: "Video Analyzer",
    desc:
      "Inspect codec, bitrate, resolution, audio streams and more. Trim, resize, rotate, change speed, mute, extract audio, and explore frame-level data.",
    cta: "Open analyzer",
  },
  {
    to: "/youtube",
    icon: Download,
    title: "YouTube Downloader",
    desc:
      "Paste a YouTube URL and download the video at the quality you want. Picks the right format automatically and streams cleanly.",
    cta: "Open downloader",
  },
];

export default function HomePage() {
  return (
    <div className="space-y-16">
      <section className="space-y-6 pt-8 text-center">
        <span className="inline-flex items-center rounded-full border border-border bg-secondary/60 px-3 py-1 text-xs font-medium text-muted-foreground">
          Free video tools, no sign-up
        </span>
        <h1 className="mx-auto max-w-3xl text-balance text-4xl font-bold tracking-tight sm:text-5xl lg:text-6xl">
          Your local lab for{" "}
          <span className="bg-gradient-to-r from-primary to-fuchsia-500 bg-clip-text text-transparent">
            video work.
          </span>
        </h1>
        <p className="mx-auto max-w-2xl text-pretty text-base text-muted-foreground sm:text-lg">
          Inspect, modify, and grab videos in seconds. VidLab puts the FFmpeg
          power tools you actually use behind a clean, fast UI.
        </p>
        <div className="flex flex-wrap items-center justify-center gap-3 pt-2">
          <Button size="lg" asChild data-testid="button-cta-analyzer">
            <Link to="/analyzer">
              Try the Analyzer
              <ArrowRight className="ml-2 h-4 w-4" />
            </Link>
          </Button>
          <Button
            size="lg"
            variant="outline"
            asChild
            data-testid="button-cta-youtube"
          >
            <Link to="/youtube">
              <Download className="mr-2 h-4 w-4" />
              YouTube Downloader
            </Link>
          </Button>
        </div>
      </section>

      <section className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {FEATURES.map(({ icon: Icon, title, desc }) => (
          <div
            key={title}
            className="rounded-xl border border-card-border bg-card p-6 shadow-sm transition-shadow hover:shadow-md"
            data-testid={`card-feature-${title.toLowerCase()}`}
          >
            <div className="mb-4 grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary">
              <Icon className="h-5 w-5" />
            </div>
            <h3 className="text-base font-semibold">{title}</h3>
            <p className="mt-1.5 text-sm text-muted-foreground">{desc}</p>
          </div>
        ))}
      </section>

      <section>
        <h2 className="mb-6 text-2xl font-bold tracking-tight">Tools</h2>
        <div className="grid gap-5 lg:grid-cols-2">
          {TOOLS.map(({ to, icon: Icon, title, desc, cta }) => (
            <Link
              key={to}
              to={to}
              data-testid={`card-tool-${to.replace("/", "")}`}
              className="group block rounded-2xl border border-card-border bg-card p-6 shadow-sm transition-all hover:-translate-y-0.5 hover:shadow-lg"
            >
              <div className="mb-4 flex items-center gap-3">
                <span className="grid h-10 w-10 place-items-center rounded-lg bg-primary/10 text-primary">
                  <Icon className="h-5 w-5" />
                </span>
                <h3 className="text-lg font-semibold">{title}</h3>
              </div>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {desc}
              </p>
              <div className="mt-5 inline-flex items-center text-sm font-medium text-primary">
                {cta}
                <ArrowRight className="ml-1 h-4 w-4 transition-transform group-hover:translate-x-0.5" />
              </div>
            </Link>
          ))}
        </div>
      </section>
    </div>
  );
}
