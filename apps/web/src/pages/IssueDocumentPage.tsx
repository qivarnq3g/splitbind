import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { FileUp, KeyRound, ShieldAlert, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { DocumentFileInput } from "../components/DocumentFileInput";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { canCreateIssuance, useSession } from "../features/auth/session";
import { createIssuance } from "../features/issuances/issuances";
import { SafeApiError } from "../features/shared/apiError";
import { UploadStage, uploadIssuancePdf, validatePdf } from "../features/uploads/uploadIssuance";

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

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
        throw new SafeApiError("Mã người nhận chưa đúng. Kiểm tra mã rồi thử lại.");
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

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <div className="page-heading-badge">
          <Sparkles size={14} aria-hidden="true" />
          <span>Cấp phát chứng thư số</span>
        </div>
        <h1>Tạo bản cấp phát</h1>
        <p>Chọn PDF và người nhận để tạo bản cấp phát riêng.</p>
      </header>

      <div className="workbench-layout">
        <section className="workbench" aria-labelledby="issuance-form-heading">
          <div className="workbench-caption">
            <h2 id="issuance-form-heading">Tệp và người nhận</h2>
            <p>Chọn tài liệu, sau đó nhập mã người nhận được cấp.</p>
          </div>

          <form className="form-stack issuance-form" onSubmit={submit} aria-busy={issuance.isPending}>
            <div className="field upload-dropzone" data-state={validationError ? "error" : file ? "success" : "default"}>
              {stage ? (
                <div className="vault-progress-glow" aria-hidden="true" />
              ) : null}
              <DocumentFileInput
                id="pdf-file"
                label="Tệp PDF"
                accept="application/pdf,.pdf"
                disabled={issuance.isPending}
                invalid={Boolean(validationError)}
                describedBy="pdf-help"
                filename={file?.name ?? null}
                onChange={selectFile}
              />
              <p className={validationError ? "field-help field-help-error" : "field-help"} id="pdf-help">
                {validationError ?? (file ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "PDF · tối đa 10 MiB · tối đa 50 trang")}
              </p>
            </div>

            <div className="field">
              <label htmlFor="recipient-id">Mã người nhận</label>
              <div className="input-with-icon">
                <span className="input-icon" aria-hidden="true"><KeyRound size={17} /></span>
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
              </div>
              <p className="field-help" id="recipient-help">Nhập mã người nhận do hệ thống cấp.</p>
            </div>

            <WorkflowSteps stage={stage} />

            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button
              className="button button-primary"
              type="submit"
              disabled={issuance.isPending}
              data-state={issuance.isPending ? "loading" : error ? "error" : "default"}
            >
              <FileUp size={18} aria-hidden="true" />
              <span>{issuance.isPending ? "Đang tạo bản cấp phát" : "Tạo bản cấp phát"}</span>
            </button>
          </form>
        </section>

        <aside className="workbench-aside" aria-label="Thông tin quy trình">
          <div className="aside-card">
            <h3>Quy trình cấp phát</h3>
            <ol className="aside-steps">
              <li>
                <strong>Kiểm tra tệp</strong>
                <span>Tính toán mã băm SHA-256 bảo vệ nội dung.</span>
              </li>
              <li>
                <strong>Nhúng dấu vết</strong>
                <span>Chèn định danh bảo mật bằng thuật toán chuyên dụng.</span>
              </li>
              <li>
                <strong>Ký số chứng nhận</strong>
                <span>Tạo chữ ký số Ed25519 cho bản kê khai toàn vẹn.</span>
              </li>
            </ol>
          </div>
          <div className="aside-card aside-tip">
            <h4>Lưu ý an toàn</h4>
            <p>Mỗi tài liệu cấp phát được tạo riêng biệt. Hãy lưu trữ bản PDF kết quả cẩn thận.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
