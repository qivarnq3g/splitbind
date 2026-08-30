import { api } from "../../api/client";
import { SafeApiError, safeApiMessage } from "../shared/apiError";

export const MAX_PDF_BYTES = 10 * 1024 * 1024;

export type UploadStage = "hashing" | "intent" | "uploading" | "finalizing";

export type UploadReady = {
  uploadId: string;
  sha256: string;
};

export function validatePdf(file: File): void {
  if (file.size > MAX_PDF_BYTES) {
    throw new SafeApiError("Tệp vượt quá giới hạn 10 MiB. Chọn tệp PDF nhỏ hơn rồi thử lại.");
  }
  const pdfName = file.name.toLocaleLowerCase().endsWith(".pdf");
  const pdfType = file.type === "" || file.type === "application/pdf";
  if (!pdfName || !pdfType) {
    throw new SafeApiError("Tệp đã chọn không phải PDF. Chọn tệp có định dạng PDF rồi thử lại.");
  }
}

export async function sha256(file: File): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function uploadPdf(
  file: File,
  kind: "issuance_input" | "verification_input",
  onStage: (stage: UploadStage) => void,
  signal?: AbortSignal,
): Promise<UploadReady> {
  validatePdf(file);
  onStage("hashing");
  const checksum = await sha256(file);

  onStage("intent");
  const intentResult = await api.POST("/api/v1/uploads", {
    body: {
      kind,
      filename: file.name,
      content_type: file.type || "application/pdf",
      size_bytes: file.size,
      sha256: checksum,
    },
    signal,
  });
  if (!intentResult.data) {
    throw new SafeApiError(safeApiMessage(intentResult.response.status, intentResult.error));
  }

  onStage("uploading");
  const uploadResponse = await fetch(intentResult.data.upload_url, {
    method: "PUT",
    headers: new Headers(intentResult.data.required_headers),
    body: file,
    credentials: "omit",
    signal,
  });
  if (!uploadResponse.ok) {
    throw new SafeApiError("Không thể tải tệp lên kho lưu trữ. Giữ nguyên tệp và thử lại.");
  }

  onStage("finalizing");
  const completeResult = await api.POST("/api/v1/uploads/{id}/complete", {
    params: { path: { id: intentResult.data.id } },
    body: { sha256: checksum },
    signal,
  });
  if (!completeResult.data) {
    throw new SafeApiError(safeApiMessage(completeResult.response.status, completeResult.error));
  }
  return { uploadId: completeResult.data.id, sha256: checksum };
}

export function uploadIssuancePdf(
  file: File,
  onStage: (stage: UploadStage) => void,
  signal?: AbortSignal,
): Promise<UploadReady> {
  return uploadPdf(file, "issuance_input", onStage, signal);
}

export function uploadVerificationPdf(
  file: File,
  onStage: (stage: UploadStage) => void,
  signal?: AbortSignal,
): Promise<UploadReady> {
  return uploadPdf(file, "verification_input", onStage, signal);
}
