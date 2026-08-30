import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";

import { api } from "../../api/client";
import { SafeApiError, safeApiMessage } from "../shared/apiError";

export const SESSION_QUERY_KEY = ["session"] as const;

export function useSession() {
  return useQuery({
    queryKey: SESSION_QUERY_KEY,
    queryFn: async ({ signal }) => {
      const result = await api.GET("/api/v1/auth/session", { signal });
      if (!result.data) throw new SafeApiError("Không thể kiểm tra phiên đăng nhập.");
      return result.data;
    },
    staleTime: 30_000,
  });
}

export function useLogin() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async (credentials: { username: string; password: string }) => {
      const result = await api.POST("/api/v1/auth/login", { body: credentials });
      if (!result.data) {
        throw new SafeApiError(safeApiMessage(result.response.status, result.error));
      }
      return result.data;
    },
    onSuccess: (session) => queryClient.setQueryData(SESSION_QUERY_KEY, session),
  });
}

export function useLogout() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: async () => {
      const result = await api.POST("/api/v1/auth/logout");
      if (!result.data) throw new SafeApiError(safeApiMessage(result.response.status, result.error));
      return result.data;
    },
    onSuccess: (session) => queryClient.setQueryData(SESSION_QUERY_KEY, session),
  });
}

export function canCreateIssuance(role: string | undefined): boolean {
  return role === "administrator" || role === "issuer";
}
