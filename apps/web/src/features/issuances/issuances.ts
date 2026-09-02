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

export async function getIssuanceResult(id: string, signal?: AbortSignal) {
  const result = await api.GET("/api/v1/issuances/{id}/result", {
    params: { path: { id } },
    signal,
    cache: "no-store",
  });
  if (!result.data) {
    if (
      result.response.status === 409
      && result.error
      && "code" in result.error
      && result.error.code === "ISSUANCE_RESULT_UNAVAILABLE"
    ) {
      throw new IssuanceResultUnavailableError();
    }
    throw new SafeApiError("Không thể tạo liên kết tải lúc này. Hãy thử lại.");
  }
  return result.data;
}

export class IssuanceResultUnavailableError extends SafeApiError {
  constructor() {
    super("Kết quả PDF không còn sẵn sàng. Hãy kiểm tra lại trạng thái hồ sơ.");
    this.name = "IssuanceResultUnavailableError";
  }
}

export function openIssuanceResult(downloadUrl: string) {
  const parsed = new URL(downloadUrl);
  if (parsed.protocol !== "http:" && parsed.protocol !== "https:") {
    throw new SafeApiError("Liên kết tải không hợp lệ. Hãy thử lại.");
  }
  const anchor = document.createElement("a");
  anchor.href = parsed.href;
  anchor.download = "splitbind-result.pdf";
  anchor.rel = "noopener noreferrer";
  anchor.click();
}
