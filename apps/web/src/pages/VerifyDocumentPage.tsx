import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileCheck, Search, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { DocumentFileInput } from "../components/DocumentFileInput";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { canCreateVerification, useSession } from "../features/auth/session";
import { SafeApiError } from "../features/shared/apiError";
import { type UploadStage, uploadVerificationPdf, validateVerificationFile } from "../features/uploads/uploadIssuance";
import { createVerification } from "../features/verifications/verifications";

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
      if (!file) throw new SafeApiError("Chưa có tệp. Chọn một tệp rồi thử lại.");
      validateVerificationFile(file);
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
          <p>Chỉ vai trò administrator hoặc verifier được tải tài liệu và bắt đầu một công việc kiểm chứng mới.</p>
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
      validateVerificationFile(selected);
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

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <div className="page-heading-badge">
          <ShieldCheck size={14} aria-hidden="true" />
          <span>Kiểm tra tính toàn vẹn</span>
        </div>
        <h1>Xác minh tài liệu</h1>
        <p>Tải tài liệu lên để xem kết quả kiểm tra kỹ thuật.</p>
      </header>

      <div className="workbench-layout">
        <section className="workbench" aria-labelledby="verification-form-heading">
          <div className="workbench-caption">
            <h2 id="verification-form-heading">Tệp cần kiểm tra</h2>
            <p>Hỗ trợ PDF, PNG và JPEG.</p>
          </div>

          <form className="form-stack" onSubmit={submit} aria-busy={verification.isPending}>
            <div className="field upload-dropzone" data-state={validationError ? "error" : file ? "success" : "default"}>
              {stage ? (
                <div className="scan-laser-wrap" aria-hidden="true">
                  <div className="scan-laser-beam" />
                </div>
              ) : null}
              <DocumentFileInput
                id="verification-pdf"
                label="Tệp cần kiểm chứng"
                accept="application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg"
                disabled={verification.isPending}
                invalid={Boolean(validationError)}
                describedBy="verification-pdf-help"
                filename={file?.name ?? null}
                onChange={selectFile}
              />
              <p className={validationError ? "field-help field-help-error" : "field-help"} id="verification-pdf-help">
                {validationError ?? (file ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "Tối đa 10 MiB · PDF tối đa 50 trang")}
              </p>
            </div>

            <WorkflowSteps stage={stage} />

            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button
              className="button button-primary"
              type="submit"
              disabled={verification.isPending}
              data-state={verification.isPending ? "loading" : error ? "error" : "default"}
            >
              <Search size={18} aria-hidden="true" />
              <span>{verification.isPending ? "Đang bắt đầu xác minh" : "Bắt đầu xác minh"}</span>
            </button>
          </form>
        </section>

        <aside className="workbench-aside" aria-label="Thông tin xác minh">
          <div className="aside-card">
            <h3>Phương thức xác minh</h3>
            <ul className="aside-features">
              <li>
                <strong>Đối chiếu mã băm</strong>
                <span>Xác nhận tệp có khớp chính xác 100% với bản phát hành hay không.</span>
              </li>
              <li>
                <strong>Kiểm tra chữ ký số</strong>
                <span>Xác thực tính hợp lệ của chữ ký Ed25519 từ máy chủ cấp phát.</span>
              </li>
              <li>
                <strong>Phát hiện chỉnh sửa</strong>
                <span>Dò quét các vùng bị can thiệp trên tài liệu.</span>
              </li>
            </ul>
          </div>
          <div className="aside-card aside-tip">
            <h4>Báo cáo kỹ thuật</h4>
            <p>Kết quả thể hiện dưới dạng bằng chứng toán học khách quan, đảm bảo tính pháp lý độc lập.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
