import { cn } from "@/lib/utils";

interface ProgressBarProps {
  /** Percentage 0-100, or null for indeterminate. */
  percent: number | null;
  label?: string;
  className?: string;
}

function formatBytes(n: number | null | undefined): string {
  if (n == null) return "";
  if (n < 1024) return `${n} B`;
  if (n < 1024 * 1024) return `${(n / 1024).toFixed(1)} KB`;
  if (n < 1024 * 1024 * 1024) return `${(n / 1024 / 1024).toFixed(1)} MB`;
  return `${(n / 1024 / 1024 / 1024).toFixed(2)} GB`;
}

export function ProgressBar({ percent, label, className }: ProgressBarProps) {
  const isDeterminate = percent != null;
  const value = isDeterminate ? Math.max(0, Math.min(100, percent)) : 0;

  return (
    <div className={cn("space-y-1.5", className)} data-testid="progress-bar">
      {label ? (
        <div className="flex items-center justify-between text-xs text-muted-foreground">
          <span>{label}</span>
          {isDeterminate ? (
            <span data-testid="progress-percent" className="font-mono tabular-nums">
              {value}%
            </span>
          ) : null}
        </div>
      ) : null}
      <div
        className="relative h-2 w-full overflow-hidden rounded-full bg-secondary"
        role="progressbar"
        aria-valuemin={0}
        aria-valuemax={100}
        aria-valuenow={isDeterminate ? value : undefined}
      >
        {isDeterminate ? (
          <div
            className="h-full rounded-full bg-primary transition-[width] duration-200 ease-out"
            style={{ width: `${value}%` }}
          />
        ) : (
          <div className="absolute inset-y-0 -left-1/3 w-1/3 animate-[slide_1.4s_ease-in-out_infinite] rounded-full bg-primary" />
        )}
      </div>
      <style>{`
        @keyframes slide {
          0% { transform: translateX(0); }
          100% { transform: translateX(400%); }
        }
      `}</style>
    </div>
  );
}

export { formatBytes };
