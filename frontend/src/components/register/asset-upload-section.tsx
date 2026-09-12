"use client";

import * as React from "react";
import { UploadCloud, X, FileText } from "lucide-react";
import { cn } from "@/lib/utils";
import { FieldError } from "@/components/ui/field";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { type AssetType, type UploadAsset } from "@/types/ingest.types";

// Single accept filter for every allowed asset type.
const ACCEPT = ".vtt,.srt,.pdf";

// Asset-type options (labels carry the file format so the choice is unambiguous).
const TYPE_OPTIONS: { value: AssetType; label: string }[] = [
  { value: "captions", label: "VTT File" },
  { value: "slides", label: "Slides (PDF)" },
  { value: "transcript", label: "Transcript (PDF)" },
];

// Guesses the modality from the file so the type selector starts on the right value.
function guessType(file: File): AssetType {
  const name = file.name.toLowerCase();
  if (name.endsWith(".vtt") || name.endsWith(".srt")) return "captions";
  return "slides"; // PDFs default to slides; user can switch to transcript
}

function formatBytes(bytes: number): string {
  if (!bytes) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  const exponent = Math.floor(Math.log(bytes) / Math.log(1024));
  return `${(bytes / Math.pow(1024, exponent)).toFixed(exponent ? 1 : 0)} ${units[exponent]}`;
}

interface AssetUploadSectionProps {
  value: UploadAsset[];
  onChange: (assets: UploadAsset[]) => void;
  error?: string;
  disabled?: boolean;
}

// One upload section: assets are added one at a time and each gets a type selector.
export function AssetUploadSection({
  value,
  onChange,
  error,
  disabled,
}: AssetUploadSectionProps) {
  const inputRef = React.useRef<HTMLInputElement>(null);
  const usedTypes = new Set(value.map((asset) => asset.type));

  const addFiles = (files: FileList | null) => {
    if (!files) return;
    const next = [...value];
    for (const file of Array.from(files)) {
      let type = guessType(file);
      // Each type can be used once; if the guess is taken, fall back to a free slot.
      if (next.some((asset) => asset.type === type)) {
        const free = TYPE_OPTIONS.map((option) => option.value).find(
          (candidate) => !next.some((asset) => asset.type === candidate)
        );
        if (!free) continue; // all four slots already filled
        type = free;
      }
      next.push({ file, type });
    }
    onChange(next);
    if (inputRef.current) inputRef.current.value = "";
  };

  const setType = (index: number, type: AssetType) =>
    onChange(value.map((asset, i) => (i === index ? { ...asset, type } : asset)));

  const remove = (index: number) =>
    onChange(value.filter((_, i) => i !== index));

  return (
    <div className="space-y-2">
      {/* SINGLE UPLOAD CONTROL */}
      <button
        type="button"
        onClick={() => inputRef.current?.click()}
        onDragOver={(event) => event.preventDefault()}
        onDrop={(event) => {
          event.preventDefault();
          if (!disabled) addFiles(event.dataTransfer.files);
        }}
        disabled={disabled}
        className={cn(
          "flex w-full flex-col items-center justify-center gap-1.5 rounded-lg border border-dashed border-input bg-transparent px-4 py-6 text-center transition-colors hover:border-border-hover hover:bg-muted/40 dark:bg-input/30 cursor-pointer disabled:pointer-events-none disabled:opacity-50",
          error && "border-destructive ring-3 ring-destructive/20"
        )}
      >
        <UploadCloud className="size-5 text-muted-foreground" />
        <span className="text-sm font-medium text-foreground">Click or drag to add an asset</span>
        <span className="text-xs text-muted-foreground">
          WebVTT/SRT or PDF — one at a time
        </span>
      </button>
      <input
        ref={inputRef}
        type="file"
        accept={ACCEPT}
        className="sr-only"
        disabled={disabled}
        onChange={(event) => addFiles(event.target.files)}
      />

      {/* ADDED ASSETS */}
      {value.length > 0 && (
        <ul className="space-y-2">
          {value.map((asset, index) => (
            <li
              key={`${asset.file.name}-${index}`}
              className="flex items-center gap-3 rounded-lg border border-input bg-muted/30 px-3 py-2.5 dark:bg-input/30"
            >
              <FileText className="size-4 shrink-0 text-primary" />
              <div className="min-w-0 flex-1">
                <p className="truncate text-sm font-medium text-foreground">{asset.file.name}</p>
                <p className="text-xs text-muted-foreground">{formatBytes(asset.file.size)}</p>
              </div>
              <Select
                items={TYPE_OPTIONS}
                value={asset.type}
                disabled={disabled}
                onValueChange={(value) => setType(index, value as AssetType)}
              >
                <SelectTrigger aria-label="Asset type" className="w-40 shrink-0">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  {TYPE_OPTIONS.map((option) => (
                    <SelectItem
                      key={option.value}
                      value={option.value}
                      disabled={option.value !== asset.type && usedTypes.has(option.value)}
                    >
                      {option.label}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <button
                type="button"
                onClick={() => remove(index)}
                disabled={disabled}
                aria-label="Remove asset"
                className="rounded p-1 text-muted-foreground transition-colors hover:text-foreground cursor-pointer disabled:pointer-events-none disabled:opacity-50"
              >
                <X className="size-4" />
              </button>
            </li>
          ))}
        </ul>
      )}

      <FieldError>{error}</FieldError>
    </div>
  );
}
