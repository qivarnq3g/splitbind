import { api } from "../../api/client";
import { SafeApiError, safeApiMessage } from "../shared/apiError";
import { formatBytes } from "../shared/formatBytes";
import { UNKNOWN_PAGE_COUNT, countPdfPages } from "./pdfPageCount";

export const MAX_PDF_BYTES = 100 * 1000 * 1000;
export const MAX_PDF_LABEL = formatBytes(MAX_PDF_BYTES);
export const MAX_PDF_PAGES = 50;

export type UploadStage = "hashing" | "intent" | "uploading" | "finalizing";

export type UploadReady = {
  uploadId: string;
  sha256: string;
};

type UploadKind = "issuance_input" | "verification_input";

function validateSize(file: File): void {
  if (file.size > MAX_PDF_BYTES) {
    throw new SafeApiError(
      `Tệp vượt quá giới hạn ${MAX_PDF_LABEL}. Chọn tệp nhỏ hơn rồi thử lại.`,
    );
  }
}

function normalizedContentType(file: File, kind: UploadKind, exactOnly = false): string | null {
  const name = file.name.toLocaleLowerCase();
  const candidates = exactOnly
    ? [{ suffixes: [".pdf"], type: "application/pdf" }]
    : [
        { suffixes: [".pdf"], type: "application/pdf" },
        { suffixes: [".png"], type: "image/png" },
        { suffixes: [".jpg", ".jpeg"], type: "image/jpeg" },
      ];
  const candidate = candidates.find(({ suffixes }) => suffixes.some((suffix) => name.endsWith(suffix)));
  if (!candidate || (file.type !== "" && file.type !== candidate.type)) return null;
  return candidate.type;
}

export function validateIssuanceFile(file: File, exactOnly = true): void {
  validateSize(file);
  if (!normalizedContentType(file, "issuance_input", exactOnly)) {
    throw new SafeApiError(
      exactOnly
        ? "Tệp đã chọn không phải PDF. Chọn tệp có định dạng PDF rồi thử lại."
        : "Tệp chưa đúng định dạng. Chọn tệp PDF, PNG hoặc JPEG rồi thử lại.",
    );
  }
}

export function validateVerificationFile(file: File, exactOnly = false): void {
  validateSize(file);
  if (!normalizedContentType(file, "verification_input", exactOnly)) {
    throw new SafeApiError(
      exactOnly
        ? "Tệp đã chọn không phải PDF. Chọn tệp có định dạng PDF rồi thử lại."
        : "Tệp chưa đúng định dạng. Chọn tệp PDF, PNG hoặc JPEG rồi thử lại.",
    );
  }
}

export async function sha256(file: File): Promise<string> {
  const digest = await globalThis.crypto.subtle.digest("SHA-256", await file.arrayBuffer());
  return Array.from(new Uint8Array(digest), (byte) => byte.toString(16).padStart(2, "0")).join("");
}

export async function uploadPdf(
  file: File,
  kind: UploadKind,
  onStage: (stage: UploadStage) => void,
  signal?: AbortSignal,
  exactOnly = false,
): Promise<UploadReady> {
  if (kind === "issuance_input") validateIssuanceFile(file, exactOnly);
  else validateVerificationFile(file, exactOnly);
  const contentType = normalizedContentType(file, kind, exactOnly)!;

  if (contentType === "application/pdf") {
    const pages = await countPdfPages(file);
    if (pages !== UNKNOWN_PAGE_COUNT && pages > MAX_PDF_PAGES) {
      throw new SafeApiError(
        `Tệp có ${pages.toLocaleString("vi-VN")} trang, vượt giới hạn ${MAX_PDF_PAGES} trang. ` +
          "Chọn tệp ngắn hơn hoặc tách bớt trang rồi thử lại.",
      );
    }
  }

  onStage("hashing");
  const checksum = await sha256(file);

  onStage("intent");
  const intentResult = await api.POST("/api/v1/uploads", {
    body: {
      kind,
      filename: file.name,
      content_type: contentType,
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
  exactOnly = true,
): Promise<UploadReady> {
  return uploadPdf(file, "issuance_input", onStage, signal, exactOnly);
}

export function uploadVerificationPdf(
  file: File,
  onStage: (stage: UploadStage) => void,
  signal?: AbortSignal,
  exactOnly = false,
): Promise<UploadReady> {
  return uploadPdf(file, "verification_input", onStage, signal, exactOnly);
}
