"use client";

import { useState } from "react";
import { useForm, Controller } from "react-hook-form";
import { ArrowRight, UploadCloud } from "lucide-react";

import { PageHeader } from "@/components/ui/page-header";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Field, FieldError, FieldLabel } from "@/components/ui/field";
import { Badge } from "@/components/ui/badge";
import { AssetUploadSection } from "@/components/register/asset-upload-section";
import { IngestionProgress } from "@/components/register/ingestion-progress";
import { useCreateIngestion } from "@/hooks/mutations/use-create-ingestion";
import { useIngestionJob } from "@/hooks/query/use-ingestion-job";
import { useIngestionJobs } from "@/hooks/query/use-ingestion-jobs";
import { type IngestFormValues } from "@/types/ingest.types";

const LABEL_CLASS = "text-xs font-semibold tracking-wider text-muted-foreground";

export default function RegisterPage() {
  const [activeJobId, setActiveJobId] = useState<string | null>(null);

  const createIngestion = useCreateIngestion();
  const { data: activeJob } = useIngestionJob(activeJobId);
  const { data: recentJobs = [] } = useIngestionJobs();

  const {
    register,
    control,
    handleSubmit,
    reset,
    formState: { errors },
  } = useForm<IngestFormValues>({
    defaultValues: {
      lecture_id: "",
      course_id: "deeplearning",
      owner: "",
      assets: [],
    },
    mode: "onTouched",
  });

  const isProcessing = createIngestion.isPending;

  // BUILD MULTIPART BODY AND TRIGGER THE BACKGROUND INGESTION JOB
  const onSubmit = (values: IngestFormValues) => {
    const formData = new FormData();
    formData.append("lecture_id", values.lecture_id);
    formData.append("course_id", values.course_id || "deeplearning");
    if (values.owner) formData.append("owner", values.owner);
    // Each asset maps to its matching backend form field (captions/slides/transcript/video).
    for (const asset of values.assets) {
      formData.append(asset.type, asset.file);
    }

    createIngestion.mutate(formData, {
      onSuccess: (job) => {
        setActiveJobId(job.job_id);
        reset({
          lecture_id: "",
          course_id: values.course_id,
          owner: values.owner,
          assets: [],
        });
      },
    });
  };

  return (
    <div className="space-y-6">
      <PageHeader
        title="Ingest Lecture Assets"
        description="Upload a lecture's captions, slides and transcript to extract, analyse and index it into the multimodal knowledge base."
      />

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        {/* INGESTION FORM */}
        <Card className="lg:col-span-2">
          <CardHeader className="border-b">
            <CardTitle>New ingestion</CardTitle>
            <CardDescription>
              Captions and slides are required. Transcript and video are optional.
            </CardDescription>
          </CardHeader>

          <CardContent>
            <form onSubmit={handleSubmit(onSubmit)} className="space-y-5">
              {/* LECTURE METADATA */}
              <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
                <Field data-invalid={!!errors.lecture_id}>
                  <FieldLabel htmlFor="lecture_id" className={LABEL_CLASS}>
                    Lecture ID <span className="text-destructive">*</span>
                  </FieldLabel>
                  <Input
                    id="lecture_id"
                    placeholder="lec01"
                    aria-invalid={!!errors.lecture_id}
                    disabled={isProcessing}
                    {...register("lecture_id", {
                      required: "Lecture ID is required",
                    })}
                  />
                  {errors.lecture_id?.message && (
                    <FieldError>{errors.lecture_id.message}</FieldError>
                  )}
                </Field>

                <Field>
                  <FieldLabel htmlFor="course_id" className={LABEL_CLASS}>
                    Course ID
                  </FieldLabel>
                  <Input
                    id="course_id"
                    placeholder="deeplearning"
                    disabled={isProcessing}
                    {...register("course_id")}
                  />
                </Field>
              </div>

              <Field>
                <FieldLabel htmlFor="owner" className={LABEL_CLASS}>
                  Owner (optional)
                </FieldLabel>
                <Input
                  id="owner"
                  type="email"
                  placeholder="educator@organization.edu"
                  disabled={isProcessing}
                  {...register("owner")}
                />
              </Field>

              {/* ASSET UPLOAD — ONE SECTION, ADD ONE ASSET AT A TIME */}
              <Field>
                <FieldLabel className={LABEL_CLASS}>
                  Assets <span className="text-destructive">*</span>
                </FieldLabel>
                <p className="text-xs text-muted-foreground">
                  Add a captions file (.vtt/.srt) and slides (.pdf) at minimum; transcript
                  (.pdf) and video are optional. Pick the type for each file after adding it.
                </p>
                <Controller
                  name="assets"
                  control={control}
                  rules={{
                    validate: (assets) => {
                      const types = assets.map((asset) => asset.type);
                      if (!types.includes("captions"))
                        return "Add a captions file (.vtt or .srt).";
                      if (!types.includes("slides")) return "Add a slides PDF.";
                      if (types.length !== new Set(types).size)
                        return "Each asset type can only be used once.";
                      return true;
                    },
                  }}
                  render={({ field, fieldState }) => (
                    <AssetUploadSection
                      value={field.value}
                      onChange={field.onChange}
                      error={fieldState.error?.message}
                      disabled={isProcessing}
                    />
                  )}
                />
              </Field>

              <Button type="submit" disabled={isProcessing} className="w-full sm:w-auto">
                {isProcessing ? (
                  <span className="flex items-center gap-2">
                    <span className="size-4 animate-spin rounded-full border-2 border-primary-foreground border-t-transparent" />
                    Starting…
                  </span>
                ) : (
                  <span className="flex items-center gap-2">
                    <UploadCloud className="size-4" />
                    Start ingestion
                    <ArrowRight className="size-4" />
                  </span>
                )}
              </Button>
            </form>
          </CardContent>
        </Card>

        {/* RIGHT RAIL — LIVE JOB + RECENT INGESTIONS */}
        <div className="space-y-6">
          {activeJob && <IngestionProgress job={activeJob} />}

          <Card>
            <CardHeader className="border-b">
              <CardTitle>Recent ingestions</CardTitle>
              <CardDescription>Latest jobs on this backend.</CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              {recentJobs.length === 0 ? (
                <p className="py-4 text-center text-sm text-muted-foreground">
                  No ingestion jobs yet.
                </p>
              ) : (
                recentJobs.slice(0, 6).map((job) => (
                  <button
                    key={job.job_id}
                    type="button"
                    onClick={() => setActiveJobId(job.job_id)}
                    className="flex w-full items-center justify-between gap-2 rounded-lg border border-border bg-muted/20 px-3 py-2 text-left transition-colors hover:bg-muted/40 cursor-pointer"
                  >
                    <div className="min-w-0">
                      <p className="truncate text-sm font-medium text-foreground">
                        {job.lecture_id}
                      </p>
                      <p className="truncate text-xs text-muted-foreground">
                        {new Date(job.created_at).toLocaleString()}
                      </p>
                    </div>
                    <Badge variant={badgeVariant(job.status)}>{job.status}</Badge>
                  </button>
                ))
              )}
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}

function badgeVariant(status: string): "info" | "success" | "destructive" | "secondary" {
  if (status === "completed") return "success";
  if (status === "failed") return "destructive";
  if (status === "running") return "info";
  return "secondary";
}
