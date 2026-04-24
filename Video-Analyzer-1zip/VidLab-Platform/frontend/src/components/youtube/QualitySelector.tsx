import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Label } from "@/components/ui/label";
import type { VideoFormat } from "@/lib/api";

interface QualitySelectorProps {
  qualities: VideoFormat[];
  value: string;
  onChange: (value: string) => void;
  disabled?: boolean;
}

export function QualitySelector({
  qualities,
  value,
  onChange,
  disabled,
}: QualitySelectorProps) {
  return (
    <div className="space-y-2">
      <Label htmlFor="quality" className="text-sm font-medium">
        Quality
      </Label>
      <Select value={value} onValueChange={onChange} disabled={disabled}>
        <SelectTrigger
          id="quality"
          data-testid="select-quality"
          className="w-full"
        >
          <SelectValue placeholder="Select quality" />
        </SelectTrigger>
        <SelectContent>
          {qualities.map((q) => (
            <SelectItem
              key={q.id}
              value={q.id}
              data-testid={`option-quality-${q.id}`}
            >
              {q.label}
              {q.height ? ` · ${q.height}p` : ""}
            </SelectItem>
          ))}
        </SelectContent>
      </Select>
    </div>
  );
}
