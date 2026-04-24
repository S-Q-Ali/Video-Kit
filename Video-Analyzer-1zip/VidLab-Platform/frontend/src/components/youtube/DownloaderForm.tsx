import { useState, FormEvent } from "react";
import { Search } from "lucide-react";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { LoadingSpinner } from "./LoadingSpinner";

interface DownloaderFormProps {
  onSubmit: (url: string) => void;
  isLoading: boolean;
  disabled?: boolean;
}

const URL_REGEX = /^(https?:\/\/)?(www\.|m\.|music\.)?(youtube\.com|youtu\.be|youtube-nocookie\.com)\/.+/i;

export function DownloaderForm({
  onSubmit,
  isLoading,
  disabled,
}: DownloaderFormProps) {
  const [url, setUrl] = useState("");
  const [validationError, setValidationError] = useState<string | null>(null);

  function handleSubmit(e: FormEvent) {
    e.preventDefault();
    const trimmed = url.trim();
    if (!trimmed) {
      setValidationError("Please paste a YouTube URL.");
      return;
    }
    if (!URL_REGEX.test(trimmed)) {
      setValidationError("That doesn't look like a YouTube URL.");
      return;
    }
    setValidationError(null);
    onSubmit(trimmed);
  }

  return (
    <form
      onSubmit={handleSubmit}
      data-testid="form-downloader"
      className="space-y-3"
      noValidate
    >
      <Label htmlFor="youtube-url" className="text-sm font-medium">
        YouTube URL
      </Label>
      <div className="flex flex-col gap-3 sm:flex-row">
        <Input
          id="youtube-url"
          name="youtube_url"
          type="url"
          inputMode="url"
          autoComplete="off"
          spellCheck={false}
          placeholder="https://www.youtube.com/watch?v=..."
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          disabled={isLoading || disabled}
          data-testid="input-youtube-url"
          className="flex-1"
        />
        <Button
          type="submit"
          disabled={isLoading || disabled}
          data-testid="button-fetch-info"
          className="sm:w-44"
        >
          {isLoading ? (
            <LoadingSpinner size="sm" />
          ) : (
            <>
              <Search className="mr-2 h-4 w-4" />
              Fetch Video Info
            </>
          )}
        </Button>
      </div>
      {validationError ? (
        <p
          className="text-sm text-destructive"
          role="alert"
          data-testid="text-validation-error"
        >
          {validationError}
        </p>
      ) : null}
    </form>
  );
}
