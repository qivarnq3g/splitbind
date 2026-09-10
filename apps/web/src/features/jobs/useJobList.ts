import { useQuery } from "@tanstack/react-query";

import { api } from "../../api/client";
import type { components } from "../../api/generated/schema";
import { SafeApiError, safeApiMessage } from "../shared/apiError";

export type JobListItem = components["schemas"]["Job"];

export function useJobList(kind?: "issuance" | "verification" | null) {
  return useQuery<JobListItem[], SafeApiError>({
    queryKey: ["jobs", kind ?? "all"],
    queryFn: async ({ signal }) => {
      const result = await api.GET("/api/v1/jobs", {
        params: {
          query: kind ? { kind } : {},
        },
        signal,
      });
      if (!result.data) {
        throw new SafeApiError(safeApiMessage(result.response.status, undefined));
      }
      return result.data;
    },
    refetchInterval: 10_000,
  });
}
