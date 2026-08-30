import { api } from "../../api/client";
import { SafeApiError, safeApiMessage } from "../shared/apiError";

export async function createIssuance(uploadId: string, recipientId: string, signal?: AbortSignal) {
  const result = await api.POST("/api/v1/issuances", {
    body: {
      upload_id: uploadId,
      recipient_id: recipientId,
      correlation_id: globalThis.crypto.randomUUID(),
    },
    signal,
  });
  if (!result.data) throw new SafeApiError(safeApiMessage(result.response.status, result.error));
  if (!result.data.job_id) {
    throw new SafeApiError("Hồ sơ đã được tạo nhưng chưa có công việc xử lý. Mở lại hồ sơ sau.");
  }
  return result.data;
}

export async function getIssuance(id: string, signal?: AbortSignal) {
  const result = await api.GET("/api/v1/issuances/{id}", {
    params: { path: { id } },
    signal,
  });
  if (!result.data) throw new SafeApiError(safeApiMessage(result.response.status, result.error));
  return result.data;
}
