import { useMutation, useQueryClient } from "@tanstack/react-query";
import api from "@/api/axios";
import toast from "react-hot-toast";
import { type IngestJob } from "@/types/ingest.types";

// MUTATION HOOK — CALLS POST /api/ingest (multipart form upload)
// Axios auto-sets the multipart Content-Type/boundary when passed a FormData.
export const useCreateIngestion = () => {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: async (formData: FormData) => {
      console.log("[useCreateIngestion] Starting ingestion job");
      const { data } = await api.post<IngestJob>("/api/ingest", formData);
      return data;
    },
    onSuccess: (data) => {
      console.log("[useCreateIngestion] Ingestion job started:", data.job_id);
      queryClient.invalidateQueries({ queryKey: ["ingestion-jobs"] });
      toast.success(`Ingestion started for ${data.lecture_id}`);
    },
    onError: (err: any) => {
      console.error("[useCreateIngestion] Failed to start ingestion:", err);
      const detail =
        err?.response?.data?.detail ||
        err?.response?.data?.message ||
        err?.message;
      toast.error(typeof detail === "string" ? detail : "Failed to start ingestion");
    },
  });
};
