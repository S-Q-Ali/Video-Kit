import { Link, useLocation } from "wouter";
import { ReactNode } from "react";
import { Film, Download, Home as HomeIcon, Github } from "lucide-react";
import { cn } from "@/lib/utils";

interface NavItem {
  to: string;
  label: string;
  icon: typeof HomeIcon;
}

const NAV: NavItem[] = [
  { to: "/", label: "Home", icon: HomeIcon },
  { to: "/analyzer", label: "Video Analyzer", icon: Film },
  { to: "/youtube", label: "YouTube Downloader", icon: Download },
];

export function Layout({ children }: { children: ReactNode }) {
  const [location] = useLocation();

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-40 w-full border-b border-border bg-background/80 backdrop-blur supports-[backdrop-filter]:bg-background/60">
        <div className="mx-auto flex h-16 max-w-7xl items-center justify-between px-4 sm:px-6 lg:px-8">
          <Link
            to="/"
            className="flex items-center gap-2 text-lg font-bold tracking-tight"
            data-testid="link-brand"
          >
            <span className="grid h-8 w-8 place-items-center rounded-lg bg-primary text-primary-foreground shadow-sm">
              V
            </span>
            <span>VidLab</span>
          </Link>

          <nav className="hidden items-center gap-1 md:flex">
            {NAV.map((item) => {
              const Icon = item.icon;
              const active =
                location === item.to ||
                (item.to !== "/" && location.startsWith(item.to));
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  data-testid={`link-nav-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                  className={cn(
                    "flex items-center gap-2 rounded-md px-3 py-2 text-sm font-medium transition-colors hover-elevate",
                    active
                      ? "bg-secondary text-foreground"
                      : "text-muted-foreground",
                  )}
                >
                  <Icon className="h-4 w-4" />
                  {item.label}
                </Link>
              );
            })}
          </nav>

          <a
            href="https://github.com"
            target="_blank"
            rel="noreferrer"
            className="hidden items-center gap-2 rounded-md px-3 py-2 text-sm text-muted-foreground hover-elevate sm:flex"
            data-testid="link-github"
          >
            <Github className="h-4 w-4" />
          </a>
        </div>

        <nav className="border-t border-border bg-background/60 md:hidden">
          <div className="mx-auto flex max-w-7xl items-center justify-around px-2">
            {NAV.map((item) => {
              const Icon = item.icon;
              const active =
                location === item.to ||
                (item.to !== "/" && location.startsWith(item.to));
              return (
                <Link
                  key={item.to}
                  to={item.to}
                  data-testid={`link-nav-mobile-${item.label.toLowerCase().replace(/\s+/g, "-")}`}
                  className={cn(
                    "flex flex-1 flex-col items-center gap-0.5 px-2 py-2 text-xs font-medium transition-colors",
                    active ? "text-primary" : "text-muted-foreground",
                  )}
                >
                  <Icon className="h-5 w-5" />
                  <span className="truncate">{item.label.split(" ")[0]}</span>
                </Link>
              );
            })}
          </div>
        </nav>
      </header>

      <main className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        {children}
      </main>

      <footer className="mx-auto mt-16 max-w-7xl px-4 py-8 text-center text-xs text-muted-foreground sm:px-6 lg:px-8">
        VidLab — free video tools, no sign-up.
      </footer>
    </div>
  );
}
