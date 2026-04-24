import { Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";

interface LoadingSpinnerProps {
  label?: string;
  className?: string;
  size?: "sm" | "md" | "lg";
}

const SIZE_MAP = {
  sm: "h-4 w-4",
  md: "h-6 w-6",
  lg: "h-8 w-8",
};

export function LoadingSpinner({
  label,
  className,
  size = "md",
}: LoadingSpinnerProps) {
  return (
    <div
      className={cn("flex items-center justify-center gap-2 text-muted-foreground", className)}
      role="status"
      aria-live="polite"
      data-testid="loading-spinner"
    >
      <Loader2 className={cn(SIZE_MAP[size], "animate-spin")} aria-hidden />
      {label ? <span className="text-sm">{label}</span> : null}
    </div>
  );
}
