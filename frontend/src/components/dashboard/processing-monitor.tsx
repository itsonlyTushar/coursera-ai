"use client";

import { Loader2 } from "lucide-react";

import { Card, CardContent } from "@/components/ui/card";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import { Progress } from "@/components/ui/progress";
import { Badge } from "@/components/ui/badge";
import { useIngestionJobs } from "@/hooks/query/use-ingestion-jobs";
import { type IngestJobStatus } from "@/types/ingest.types";

const STATUS_VARIANT: Record<IngestJobStatus, "info" | "success" | "destructive" | "secondary"> = {
  queued: "secondary",
  running: "info",
  completed: "success",
  failed: "destructive",
};

// Live table of ingestion jobs with a per-row progress bar.
export function ProcessingMonitor() {
  const { data: jobs = [], isLoading } = useIngestionJobs();

  return (
    <Card>
      <CardContent className="px-0">
        <Table>
          <TableHeader>
            <TableRow>
              <TableHead>Lecture</TableHead>
              <TableHead>Course</TableHead>
              <TableHead>Stage</TableHead>
              <TableHead className="w-[220px]">Progress</TableHead>
              <TableHead>Status</TableHead>
              <TableHead className="text-right">Updated</TableHead>
            </TableRow>
          </TableHeader>
          <TableBody>
            {jobs.length === 0 ? (
              <TableRow>
                <TableCell colSpan={6} className="py-10 text-center text-muted-foreground">
                  {isLoading ? "Loading jobs…" : "No ingestion jobs yet."}
                </TableCell>
              </TableRow>
            ) : (
              jobs.map((job) => {
                const pct = Math.round((job.progress ?? 0) * 100);
                const failed = job.status === "failed";
                const active = job.status === "running" || job.status === "queued";
                return (
                  <TableRow key={job.job_id}>
                    <TableCell className="font-medium text-foreground">{job.lecture_id}</TableCell>
                    <TableCell className="text-muted-foreground">{job.course_id}</TableCell>
                    <TableCell className="capitalize text-muted-foreground">
                      {job.stage.replace(/_/g, " ")}
                    </TableCell>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        <Progress
                          value={pct}
                          indicatorClassName={failed ? "bg-destructive" : undefined}
                          className="w-40"
                        />
                        <span className="w-9 text-right text-xs tabular-nums text-muted-foreground">
                          {pct}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell>
                      <Badge variant={STATUS_VARIANT[job.status]}>
                        {active && <Loader2 className="size-3 animate-spin" />}
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground">
                      {new Date(job.updated_at).toLocaleTimeString()}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>
      </CardContent>
    </Card>
  );
}
