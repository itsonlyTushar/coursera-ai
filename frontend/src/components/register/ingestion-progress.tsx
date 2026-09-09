"use client";

import { CheckCircle2, XCircle, Loader2 } from "lucide-react";
import { cn } from "@/lib/utils";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { type IngestJob, type IngestJobStatus } from "@/types/ingest.types";

type BadgeVariant = "info" | "success" | "destructive" | "secondary";

const STATUS_META: Record<IngestJobStatus, { label: string; variant: BadgeVariant }> = {
  queued: { label: "Queued", variant: "secondary" },
  running: { label: "Running", variant: "info" },
  completed: { label: "Completed", variant: "success" },
  failed: { label: "Failed", variant: "destructive" },
};

// Live status card for one ingestion job: progress bar, stage, result counts or error.
export function IngestionProgress({ job }: { job: IngestJob }) {
  const meta = STATUS_META[job.status] ?? STATUS_META.queued;
  const pct = Math.round((job.progress ?? 0) * 100);
  const active = job.status === "queued" || job.status === "running";

  return (
    <Card>
      <CardHeader className="flex flex-row items-center justify-between">
        <CardTitle className="flex items-center gap-2">
          {active && <Loader2 className="size-4 animate-spin text-primary" />}
          {job.status === "completed" && <CheckCircle2 className="size-4 text-emerald-500" />}
          {job.status === "failed" && <XCircle className="size-4 text-destructive" />}
          {job.lecture_id}
        </CardTitle>
        <Badge variant={meta.variant}>{meta.label}</Badge>
      </CardHeader>

      <CardContent className="space-y-3">
        <div className="space-y-1.5">
          <div className="flex items-center justify-between text-xs text-muted-foreground">
            <span className="capitalize">{job.stage.replace(/_/g, " ")}</span>
            <span>{pct}%</span>
          </div>
          <div className="h-2 w-full overflow-hidden rounded-full bg-muted">
            <div
              className={cn(
                "h-full rounded-full transition-all",
                job.status === "failed" ? "bg-destructive" : "bg-primary"
              )}
              style={{ width: `${pct}%` }}
            />
          </div>
          {job.message && <p className="text-xs text-muted-foreground">{job.message}</p>}
        </div>

        {job.status === "completed" && (
          <div className="grid grid-cols-3 gap-2 text-center">
            <Stat label="Captions" value={job.result?.caption_records} />
            <Stat label="Slides" value={job.result?.slide_records} />
            <Stat label="Points" value={job.result?.points_upserted} />
          </div>
        )}

        {job.status === "failed" && job.error && (
          <Alert variant="destructive">
            <XCircle className="size-4" />
            <AlertTitle>Ingestion failed</AlertTitle>
            <AlertDescription>{job.error}</AlertDescription>
          </Alert>
        )}
      </CardContent>
    </Card>
  );
}

function Stat({ label, value }: { label: string; value?: number }) {
  return (
    <div className="rounded-lg border border-border bg-muted/30 py-2">
      <p className="text-lg font-semibold text-foreground">{value ?? 0}</p>
      <p className="text-xs text-muted-foreground">{label}</p>
    </div>
  );
}
