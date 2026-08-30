import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { canCreateIssuance, useSession } from "../features/auth/session";
import { createIssuance } from "../features/issuances/issuances";
import { SafeApiError } from "../features/shared/apiError";
import { UploadStage, uploadIssuancePdf, validatePdf } from "../features/uploads/uploadIssuance";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;
const STAGE_STEP: Record<UploadStage, number> = {
  hashing: 1,
  intent: 2,
  uploading: 3,
  finalizing: 4,
};
const STAGE_LABEL: Record<UploadStage, string> = {
  hashing: "Đang kiểm tra tệp",
  intent: "Đang tạo phiên tải lên",
  uploading: "Đang tải tệp",
  finalizing: "Đang xác nhận tệp",
};

export function IssueDocumentPage() {
  const session = useSession();
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [recipientId, setRecipientId] = useState("");
  const [stage, setStage] = useState<UploadStage | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const issuance = useMutation({
    mutationFn: async () => {
      if (!file) throw new SafeApiError("Chưa có tệp PDF. Chọn một tệp rồi thử lại.");
      validatePdf(file);
      if (!UUID_PATTERN.test(recipientId)) {
        throw new SafeApiError("Mã người nhận chưa đúng định dạng UUID. Kiểm tra mã rồi thử lại.");
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const upload = await uploadIssuancePdf(file, setStage, controller.signal);
      setStage(null);
      return createIssuance(upload.uploadId, recipientId, controller.signal);
    },
    onSuccess: (created) => navigate(`/jobs/${created.job_id}`, {
      state: { issuanceId: created.id },
    }),
    onSettled: () => setStage(null),
  });

  const role = session.data?.user?.role;
  if (!canCreateIssuance(role)) {
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Quyền chỉ đọc</h1>
          <p>Vai trò {role ?? "hiện tại"} có thể xem hồ sơ được cấp quyền nhưng không thể tạo bản cấp phát.</p>
        </header>
      </main>
    );
  }

  function selectFile(selected: File | undefined) {
    setValidationError(null);
    issuance.reset();
    if (!selected) {
      setFile(null);
      return;
    }
    try {
      validatePdf(selected);
      setFile(selected);
    } catch (error) {
      setFile(selected);
      setValidationError(error instanceof Error ? error.message : "Tệp chưa hợp lệ.");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    issuance.mutate();
  }

  const error = validationError ?? issuance.error?.message ?? null;
  const progressStep = stage ? STAGE_STEP[stage] : 0;

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <h1>Tạo bản cấp phát</h1>
        <p>Chọn một PDF, nhập mã người nhận trong tổ chức và theo dõi công việc xử lý.</p>
      </header>

      <section className="workbench" aria-labelledby="issuance-form-heading">
        <div className="workbench-caption">
          <h2 id="issuance-form-heading">Thông tin đầu vào</h2>
          <p>Giới hạn phía trình duyệt là 10 MiB. Máy chủ và worker vẫn kiểm tra lại nội dung.</p>
        </div>
        <form className="form-stack issuance-form" onSubmit={submit} aria-busy={issuance.isPending}>
          <div className="field" data-state={validationError ? "error" : file ? "success" : "default"}>
            <label htmlFor="pdf-file">Tệp PDF</label>
            <input
              className="file-control"
              id="pdf-file"
              name="pdf-file"
              type="file"
              accept="application/pdf,.pdf"
              required
              disabled={issuance.isPending}
              aria-invalid={Boolean(validationError)}
              aria-describedby="pdf-help"
              onChange={(event) => selectFile(event.target.files?.[0])}
            />
            <p className={validationError ? "field-help field-help-error" : "field-help"} id="pdf-help">
              {validationError ?? (file ? `${file.name} · ${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "PDF tối đa 10 MiB và 50 trang; worker xác minh định dạng thực tế.")}
            </p>
          </div>

          <div className="field">
            <label htmlFor="recipient-id">Mã người nhận</label>
            <input
              id="recipient-id"
              name="recipient-id"
              inputMode="text"
              autoComplete="off"
              required
              disabled={issuance.isPending}
              aria-invalid={recipientId !== "" && !UUID_PATTERN.test(recipientId)}
              aria-describedby="recipient-help"
              placeholder="00000000-0000-0000-0000-000000000000"
              value={recipientId}
              onChange={(event) => setRecipientId(event.target.value.trim())}
            />
            <p className="field-help" id="recipient-help">API hiện nhận UUID người nhận; chưa có endpoint danh sách để chọn.</p>
          </div>

          <div className="progress-slot" aria-live="polite">
            {stage ? (
              <>
                <div className="progress-copy"><span>{STAGE_LABEL[stage]}</span><span>Bước {progressStep}/4</span></div>
                <progress max="4" value={progressStep}>Bước {progressStep}/4</progress>
              </>
            ) : <p>Quy trình chỉ bắt đầu khi bạn xác nhận tạo bản cấp phát.</p>}
          </div>

          {error ? <p className="form-error" role="alert">{error}</p> : <p className="form-error" aria-hidden="true">&nbsp;</p>}
          <button className="button button-primary" type="submit" disabled={issuance.isPending} data-state={issuance.isPending ? "loading" : error ? "error" : "default"}>
            {issuance.isPending ? "Đang tạo bản cấp phát" : "Tạo bản cấp phát"}
          </button>
        </form>
      </section>
    </main>
  );
}
