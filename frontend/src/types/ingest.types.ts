// INGESTION API TYPES (POST /api/ingest, GET /api/ingest, GET /api/ingest/{job_id})

export type IngestJobStatus = "queued" | "running" | "completed" | "failed";

export interface IngestJobResult {
  lecture_id?: string;
  course_id?: string;
  caption_records?: number;
  slide_records?: number;
  points_upserted?: number;
  collection?: string;
}

export interface IngestJob {
  job_id: string;
  status: IngestJobStatus;
  stage: string;
  progress: number; // 0..1
  lecture_id: string;
  course_id: string;
  owner?: string | null;
  message: string;
  error?: string | null;
  result: IngestJobResult;
  created_at: string;
  updated_at: string;
}

export interface IngestJobList {
  jobs: IngestJob[];
}

// ASSET TYPES ACCEPTED BY THE INGESTION ENDPOINT (map 1:1 to backend form fields)
export type AssetType = "captions" | "slides" | "transcript" | "video";

// ONE UPLOADED ASSET: a file plus the modality it should be ingested as
export interface UploadAsset {
  file: File;
  type: AssetType;
}

// REACT HOOK FORM VALUES FOR THE INGESTION FORM
export interface IngestFormValues {
  lecture_id: string;
  course_id: string;
  owner?: string;
  assets: UploadAsset[];
}
