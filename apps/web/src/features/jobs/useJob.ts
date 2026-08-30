import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import { SafeApiError, safeApiMessage } from "../shared/apiError";

export const TERMINAL_JOB_STATUSES = new Set(["succeeded", "failed", "dead_lettered", "cancelled"]);

export function jobPollingInterval(status: string | undefined, completedPolls: number, failures: number): number | false {
  if (status && TERMINAL_JOB_STATUSES.has(status)) return false;
  const exponent = Math.max(completedPolls - 1, failures, 0);
  return Math.min(1_000 * 2 ** exponent, 5_000);
}

export function useJob(jobId: string | null) {
  return useQuery({
    queryKey: ["job", jobId],
    queryFn: async ({ signal }) => {
      const result = await api.GET("/api/v1/jobs/{id}", {
        params: { path: { id: jobId! } },
        signal,
      });
      if (!result.data) throw new SafeApiError(safeApiMessage(result.response.status, result.error));
      return result.data;
    },
    enabled: jobId !== null,
    refetchInterval: (query) => jobPollingInterval(
      query.state.data?.status,
      query.state.dataUpdateCount,
      query.state.fetchFailureCount,
    ),
  });
}

export const JOB_LABELS: Record<string, string> = {
  created: "Đã tạo",
  queued: "Đang chờ",
  processing: "Đang xử lý",
  retryable_failed: "Đang thử lại",
  succeeded: "Hoàn tất",
  failed: "Thất bại",
  dead_lettered: "Dừng sau nhiều lần thử",
  cancelled: "Đã hủy",
};
