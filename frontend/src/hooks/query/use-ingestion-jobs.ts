import { useQuery } from "@tanstack/react-query";
import api from "@/api/axios";
import { type IngestJob, type IngestJobList } from "@/types/ingest.types";

// QUERY HOOK — CALLS GET /api/ingest (recent ingestion jobs)
export const useIngestionJobs = () => {
  return useQuery<IngestJob[]>({
    queryKey: ["ingestion-jobs"],
    queryFn: async () => {
      const { data } = await api.get<IngestJobList>("/api/ingest");
      return data.jobs ?? [];
    },
    staleTime: 10_000,
    refetchInterval: 5_000, // keep the recent list fresh while jobs run
  });
};
