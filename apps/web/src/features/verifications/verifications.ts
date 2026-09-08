import { api } from "../../api/client";
import { SafeApiError, safeApiMessage } from "../shared/apiError";

export async function createVerification(uploadId: string, signal?: AbortSignal) {
  const result = await api.POST("/api/v1/verifications", {
    body: {
      upload_id: uploadId,
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

export async function getVerification(id: string, signal?: AbortSignal) {
  const result = await api.GET("/api/v1/verifications/{id}", {
    params: { path: { id } },
    signal,
  });
  if (!result.data) throw new SafeApiError(safeApiMessage(result.response.status, result.error));
  return result.data;
}
