import { useQuery } from "@tanstack/react-query";
import api from "@/api/axios";
import { type IngestJob } from "@/types/ingest.types";

// QUERY HOOK — POLLS GET /api/ingest/{job_id} UNTIL THE JOB IS DONE
export const useIngestionJob = (jobId: string | null) => {
  return useQuery<IngestJob>({
    queryKey: ["ingestion-job", jobId],
    queryFn: async () => {
      const { data } = await api.get<IngestJob>(`/api/ingest/${jobId}`);
      return data;
    },
    enabled: !!jobId,
    // Poll while queued/running; stop once terminal.
    refetchInterval: (query) => {
      const status = query.state.data?.status;
      return status === "completed" || status === "failed" ? false : 1500;
    },
  });
};
