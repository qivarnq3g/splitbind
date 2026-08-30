import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useNavigate } from "react-router-dom";

import { canCreateVerification, useSession } from "../features/auth/session";
import { SafeApiError } from "../features/shared/apiError";
import { type UploadStage, uploadVerificationPdf, validatePdf } from "../features/uploads/uploadIssuance";
import { createVerification } from "../features/verifications/verifications";

const STAGE_STEP: Record<UploadStage, number> = { hashing: 1, intent: 2, uploading: 3, finalizing: 4 };
const STAGE_LABEL: Record<UploadStage, string> = {
  hashing: "Đang kiểm tra tệp",
  intent: "Đang tạo phiên tải lên",
  uploading: "Đang tải tệp",
  finalizing: "Đang xác nhận tệp",
};

export function VerifyDocumentPage() {
  const session = useSession();
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<UploadStage | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const verification = useMutation({
    mutationFn: async () => {
      if (!file) throw new SafeApiError("Chưa có tệp PDF. Chọn một tệp rồi thử lại.");
      validatePdf(file);
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const upload = await uploadVerificationPdf(file, setStage, controller.signal);
      setStage(null);
      return createVerification(upload.uploadId, controller.signal);
    },
    onSuccess: (created) => navigate(`/jobs/${created.job_id}`, {
      state: { verificationId: created.id },
    }),
    onSettled: () => setStage(null),
  });

  const role = session.data?.user?.role;
  if (!canCreateVerification(role)) {
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Không có quyền tạo kiểm chứng</h1>
          <p>Chỉ vai trò verifier được tải tài liệu và bắt đầu một công việc kiểm chứng mới.</p>
        </header>
      </main>
    );
  }

  function selectFile(selected: File | undefined) {
    setValidationError(null);
    verification.reset();
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
    verification.mutate();
  }

  const error = validationError ?? verification.error?.message ?? null;
  const progressStep = stage ? STAGE_STEP[stage] : 0;

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <h1>Xác minh tài liệu</h1>
        <p>Tải một PDF nghi vấn để kiểm tra dấu vân tay, manifest và tín hiệu toàn vẹn trong phạm vi hệ thống cung cấp.</p>
      </header>
      <section className="workbench" aria-labelledby="verification-form-heading">
        <div className="workbench-caption">
          <h2 id="verification-form-heading">Tài liệu cần kiểm chứng</h2>
          <p>Trình duyệt giới hạn tệp ở 10 MiB. Máy chủ và worker vẫn phải xác minh lại nội dung thực tế.</p>
        </div>
        <form className="form-stack" onSubmit={submit} aria-busy={verification.isPending}>
          <div className="field" data-state={validationError ? "error" : file ? "success" : "default"}>
            <label htmlFor="verification-pdf">Tệp PDF cần kiểm chứng</label>
            <input
              className="file-control"
              id="verification-pdf"
              name="verification-pdf"
              type="file"
              accept="application/pdf,.pdf"
              required
              disabled={verification.isPending}
              aria-invalid={Boolean(validationError)}
              aria-describedby="verification-pdf-help"
              onChange={(event) => selectFile(event.target.files?.[0])}
            />
            <p className={validationError ? "field-help field-help-error" : "field-help"} id="verification-pdf-help">
              {validationError ?? (file ? `${file.name} · ${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "PDF tối đa 10 MiB và 50 trang; worker xác minh định dạng thực tế.")}
            </p>
          </div>
          <div className="progress-slot" aria-live="polite">
            {stage ? (
              <>
                <div className="progress-copy"><span>{STAGE_LABEL[stage]}</span><span>Bước {progressStep}/4</span></div>
                <progress max="4" value={progressStep}>Bước {progressStep}/4</progress>
              </>
            ) : <p>Quy trình chỉ bắt đầu khi bạn xác nhận tài liệu cần kiểm chứng.</p>}
          </div>
          {error ? <p className="form-error" role="alert">{error}</p> : <p className="form-error" aria-hidden="true">&nbsp;</p>}
          <button className="button button-primary" type="submit" disabled={verification.isPending} data-state={verification.isPending ? "loading" : error ? "error" : "default"}>
            {verification.isPending ? "Đang bắt đầu xác minh" : "Bắt đầu xác minh"}
          </button>
        </form>
      </section>
    </main>
  );
}
