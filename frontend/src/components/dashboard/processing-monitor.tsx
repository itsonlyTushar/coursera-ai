"use client";

import React, { useState, useMemo } from "react";
import Link from "next/link";
import {
  Loader2,
  RefreshCw,
  Cpu,
  AlertCircle,
  Inbox,
  ChevronLeft,
  ChevronRight,
  ArrowUpRight,
  CheckCircle2,
  XCircle,
  Clock,
} from "lucide-react";

import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
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
import { Button } from "@/components/ui/button";
import { Skeleton } from "@/components/ui/skeleton";
import { useIngestionJobs } from "@/hooks/query/use-ingestion-jobs";
import { type IngestJobStatus } from "@/types/ingest.types";

const STATUS_VARIANT: Record<
  IngestJobStatus,
  "info" | "success" | "destructive" | "secondary"
> = {
  queued: "secondary",
  running: "info",
  completed: "success",
  failed: "destructive",
};

export interface ProcessingMonitorProps {
  isLoading?: boolean;
}

export function ProcessingMonitor({
  isLoading: externalLoading,
}: ProcessingMonitorProps = {}) {
  const {
    data: jobs = [],
    isLoading: isQueryLoading,
    isFetching,
    isError,
    error,
    refetch,
  } = useIngestionJobs();

  const [page, setPage] = useState(1);
  const pageSize = 8;

  const isLoading =
    externalLoading !== undefined ? externalLoading : isQueryLoading;

  // Active / Completed / Failed telemetry counts
  const activeCount = useMemo(
    () =>
      jobs.filter((j) => j.status === "running" || j.status === "queued")
        .length,
    [jobs],
  );
  const completedCount = useMemo(
    () => jobs.filter((j) => j.status === "completed").length,
    [jobs],
  );
  const failedCount = useMemo(
    () => jobs.filter((j) => j.status === "failed").length,
    [jobs],
  );

  const totalPages = Math.max(1, Math.ceil(jobs.length / pageSize));
  const paginatedJobs = useMemo(() => {
    const start = (page - 1) * pageSize;
    return jobs.slice(start, start + pageSize);
  }, [jobs, page, pageSize]);

  // SKELETON LOADING STATE
  if (isLoading && jobs.length === 0) {
    return (
      <Card className="border-border/80 shadow-xs">
        <CardHeader className="border-b border-border/40 pb-4">
          <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
            <div className="flex items-center gap-2.5">
              <div className="p-2 rounded-md bg-muted text-primary border border-border/50">
                <Cpu className="w-5 h-5" />
              </div>
              <div>
                <CardTitle className="text-base font-heading">
                  Ingestion Processing Monitor
                </CardTitle>
                <CardDescription className="text-xs mt-0.5">
                  Real-time multimodal extraction telemetry, vectorization
                  progress, and ingestion runs.
                </CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-2 self-start sm:self-auto">
              <Skeleton className="h-6 w-20 rounded-full" />
              <Skeleton className="h-6 w-24 rounded-full" />
            </div>
          </div>
        </CardHeader>

        <CardContent className="px-0 py-0">
          <Table>
            <TableHeader>
              <TableRow className="border-border/50">
                <TableHead>Lecture</TableHead>
                <TableHead>Course</TableHead>
                <TableHead>Stage</TableHead>
                <TableHead className="w-[220px]">Progress</TableHead>
                <TableHead>Status</TableHead>
                <TableHead className="text-right">Updated</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[...Array(5)].map((_, i) => (
                <TableRow
                  key={i}
                  className="hover:bg-transparent border-border/40"
                >
                  <TableCell className="py-3.5">
                    <Skeleton className="h-4 w-28" />
                  </TableCell>
                  <TableCell className="py-3.5">
                    <Skeleton className="h-4 w-20" />
                  </TableCell>
                  <TableCell className="py-3.5">
                    <Skeleton className="h-4 w-24" />
                  </TableCell>
                  <TableCell className="py-3.5">
                    <div className="flex items-center gap-2">
                      <Skeleton className="h-2 w-36 rounded-full" />
                      <Skeleton className="h-3 w-8" />
                    </div>
                  </TableCell>
                  <TableCell className="py-3.5">
                    <Skeleton className="h-5 w-20 rounded-full" />
                  </TableCell>
                  <TableCell className="py-3.5 text-right">
                    <Skeleton className="h-3.5 w-16 ml-auto" />
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    );
  }

  // ERROR STATE
  if (isError && jobs.length === 0) {
    return (
      <Card className="border-destructive/30 bg-destructive/5 shadow-xs">
        <CardContent className="p-6">
          <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
            <div className="flex items-start gap-3">
              <div className="p-2 rounded-md bg-destructive/10 text-destructive border border-destructive/20 mt-0.5">
                <AlertCircle className="w-5 h-5" />
              </div>
              <div>
                <h3 className="text-sm font-semibold text-destructive">
                  Failed to fetch ingestion telemetry
                </h3>
                <p className="text-xs text-muted-foreground mt-0.5">
                  {error instanceof Error
                    ? error.message
                    : "Unable to reach the ingestion manager service. Ensure the backend is active."}
                </p>
              </div>
            </div>
            <Button
              variant="outline"
              size="sm"
              onClick={() => refetch()}
              className="gap-1.5 shrink-0 h-8 text-xs border-destructive/30 hover:bg-destructive/10"
            >
              <RefreshCw className="w-3.5 h-3.5" />
              Retry Fetch
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="border-border/80 shadow-xs">
      <CardHeader className="border-b border-border/40 pb-4">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3">
          <div className="flex items-center gap-2.5">
            <div className="p-2 rounded-md bg-muted text-primary border border-border/50">
              <Cpu className="w-5 h-5" />
            </div>
            <div>
              <CardTitle className="text-base font-heading">
                Ingestion Processing Monitor
              </CardTitle>
              <CardDescription className="text-xs mt-0.5">
                Real-time multimodal extraction telemetry, vectorization
                progress, and ingestion runs.
              </CardDescription>
            </div>
          </div>

          <div className="flex items-center gap-2 self-start sm:self-auto shrink-0">
            {/* ACTIVE IN-FLIGHT JOBS BADGE */}
            {activeCount > 0 ? (
              <Badge
                variant="info"
                className="gap-1.5 animate-pulse text-[11px] px-2 py-0.5"
              >
                <Loader2 className="w-3 h-3 animate-spin" />
                {activeCount} active
              </Badge>
            ) : (
              <Badge
                variant="secondary"
                className="text-[11px] px-2 py-0.5 gap-1"
              >
                <CheckCircle2 className="w-3 h-3 text-emerald-500" />
                {completedCount} completed
              </Badge>
            )}

            {failedCount > 0 && (
              <Badge
                variant="destructive"
                className="text-[11px] px-2 py-0.5 gap-1"
              >
                <XCircle className="w-3 h-3" />
                {failedCount} failed
              </Badge>
            )}

            <Badge
              variant="outline"
              className="text-[11px] px-2 py-0.5 text-muted-foreground"
            >
              {jobs.length} total
            </Badge>

            <Button
              variant="ghost"
              size="sm"
              onClick={() => refetch()}
              disabled={isFetching}
              title="Refresh ingestion jobs"
              className="h-7 w-7 p-0 ml-1 text-muted-foreground hover:text-foreground"
            >
              <RefreshCw
                className={`w-3.5 h-3.5 ${isFetching ? "animate-spin text-primary" : ""}`}
              />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="px-0 py-0">
        <Table>
          <TableHeader>
            <TableRow className="border-border/50">
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
                <TableCell colSpan={6} className="py-12 text-center">
                  <div className="flex flex-col items-center justify-center gap-2 max-w-sm mx-auto">
                    <div className="p-3 rounded-full bg-muted/60 text-muted-foreground border border-border/40">
                      <Inbox className="w-6 h-6" />
                    </div>
                    <p className="text-sm font-medium text-foreground">
                      No ingestion jobs yet
                    </p>
                    <p className="text-xs text-muted-foreground leading-relaxed">
                      Course ingestion jobs submitted through the registration
                      portal or automated scripts will appear here with
                      real-time status and progress.
                    </p>
                    <Link href="/register" className="mt-2">
                      <Button
                        variant="outline"
                        size="sm"
                        className="gap-1.5 text-xs h-8"
                      >
                        Upload Course Material
                        <ArrowUpRight className="w-3.5 h-3.5" />
                      </Button>
                    </Link>
                  </div>
                </TableCell>
              </TableRow>
            ) : (
              paginatedJobs.map((job) => {
                const pct = Math.round((job.progress ?? 0) * 100);
                const failed = job.status === "failed";
                const active =
                  job.status === "running" || job.status === "queued";
                return (
                  <TableRow
                    key={job.job_id}
                    className="border-border/40 hover:bg-muted/30 transition-colors"
                  >
                    <TableCell className="font-medium text-foreground py-3">
                      <span className="font-mono text-xs">
                        {job.lecture_id}
                      </span>
                    </TableCell>
                    <TableCell className="text-muted-foreground text-xs py-3">
                      {job.course_id}
                    </TableCell>
                    <TableCell className="capitalize text-muted-foreground text-xs py-3">
                      {job.stage ? job.stage.replace(/_/g, " ") : "queued"}
                    </TableCell>
                    <TableCell className="py-3">
                      <div className="flex items-center gap-2">
                        <Progress
                          value={pct}
                          indicatorClassName={
                            failed ? "bg-destructive" : undefined
                          }
                          className="w-36 h-2"
                        />
                        <span className="w-8 text-right text-xs tabular-nums text-muted-foreground">
                          {pct}%
                        </span>
                      </div>
                    </TableCell>
                    <TableCell className="py-3">
                      <Badge
                        variant={STATUS_VARIANT[job.status]}
                        className="text-[11px] gap-1 px-2 py-0.5"
                      >
                        {active && <Loader2 className="w-3 h-3 animate-spin" />}
                        {job.status}
                      </Badge>
                    </TableCell>
                    <TableCell className="text-right text-xs text-muted-foreground py-3 tabular-nums">
                      {new Date(job.updated_at).toLocaleTimeString([], {
                        hour: "2-digit",
                        minute: "2-digit",
                        second: "2-digit",
                      })}
                    </TableCell>
                  </TableRow>
                );
              })
            )}
          </TableBody>
        </Table>

        {/* PAGINATION CONTROLS */}
        {jobs.length > pageSize && (
          <div className="flex items-center justify-between px-4 py-3 border-t border-border/40 bg-muted/10 text-xs text-muted-foreground">
            <div>
              Showing{" "}
              <span className="font-medium text-foreground">
                {(page - 1) * pageSize + 1}
              </span>{" "}
              to{" "}
              <span className="font-medium text-foreground">
                {Math.min(page * pageSize, jobs.length)}
              </span>{" "}
              of{" "}
              <span className="font-medium text-foreground">{jobs.length}</span>{" "}
              jobs
            </div>
            <div className="flex items-center gap-1.5">
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.max(1, p - 1))}
                disabled={page <= 1}
                className="h-7 px-2 text-xs"
              >
                <ChevronLeft className="w-3.5 h-3.5 mr-1" />
                Previous
              </Button>
              <span className="text-xs px-2 tabular-nums">
                {page} / {totalPages}
              </span>
              <Button
                variant="outline"
                size="sm"
                onClick={() => setPage((p) => Math.min(totalPages, p + 1))}
                disabled={page >= totalPages}
                className="h-7 px-2 text-xs"
              >
                Next
                <ChevronRight className="w-3.5 h-3.5 ml-1" />
              </Button>
            </div>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
