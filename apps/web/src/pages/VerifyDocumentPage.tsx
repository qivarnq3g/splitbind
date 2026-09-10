import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { DocumentFileInput } from "../components/DocumentFileInput";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { canCreateVerification, useSession } from "../features/auth/session";
import { SafeApiError } from "../features/shared/apiError";
import {
  type UploadStage,
  uploadVerificationPdf,
  validateVerificationFile,
} from "../features/uploads/uploadIssuance";
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
      if (!file)
        throw new SafeApiError("Chưa có tệp. Chọn một tệp rồi thử lại.");
      validateVerificationFile(file);
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const upload = await uploadVerificationPdf(
        file,
        setStage,
        controller.signal,
      );
      setStage(null);
      return createVerification(upload.uploadId, controller.signal);
    },
    onSuccess: (created) =>
      navigate(`/jobs/${created.job_id}`, {
        state: { verificationId: created.id },
      }),
    onSettled: () => setStage(null),
  });

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
      setValidationError(
        error instanceof Error ? error.message : "Tệp chưa hợp lệ.",
      );
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (validationError) return;
    verification.mutate();
  }

  const error = validationError ?? verification.error?.message ?? null;

  if (!canCreateVerification(session.data?.user?.role))
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Không có quyền tạo kiểm chứng</h1>
          <p>
            Vai trò hiện tại không được phép thực hiện thao tác này. Mở hồ sơ
            bằng liên kết được cấp hoặc liên hệ quản trị viên.
          </p>
        </header>
        <Link className="button button-secondary" to="/">
          Về trang làm việc
        </Link>
      </main>
    );
  return (
    <main className="workspace-page">
      <header className="page-heading">
        <p className="page-context">Kiểm tra toàn vẹn</p>
        <h1>Xác minh tài liệu</h1>
        <p>Tải tài liệu lên để xem kết quả kiểm tra kỹ thuật.</p>
      </header>
      <div className="workbench-layout">
        <section className="workbench" aria-label="Xác minh tài liệu">
          <form
            className="form-stack"
            onSubmit={submit}
            aria-busy={verification.isPending}
          >
            <div
              className="field upload-dropzone"
              data-state={
                validationError ? "error" : file ? "success" : "default"
              }
            >
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
              <p
                className={
                  validationError ? "field-help field-help-error" : "field-help"
                }
                id="verification-pdf-help"
              >
                {validationError ??
                  (file
                    ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB · Tệp được chọn trên thiết bị, chưa tải lên.`
                    : "PDF, PNG hoặc JPEG · tối đa 10 MiB · PDF tối đa 50 trang")}
              </p>
            </div>

            <WorkflowSteps stage={stage} />
            {error ? (
              <p className="form-error" role="alert">
                {error}
              </p>
            ) : null}
            <div className="form-actions">
              <button
                className="button button-primary"
                type="submit"
                disabled={verification.isPending || Boolean(validationError)}
                data-state={
                  verification.isPending
                    ? "loading"
                    : error
                      ? "error"
                      : "default"
                }
              >
                <span>
                  {verification.isPending
                    ? "Đang bắt đầu xác minh"
                    : "Bắt đầu xác minh"}
                </span>
                <ArrowRight size={18} aria-hidden="true" />
              </button>
              <p>Kết luận xuất hiện sau khi xử lý.</p>
            </div>
          </form>
        </section>
        <aside className="task-guide" aria-label="Thông tin xác minh">
          <h2>Đối chiếu, không phỏng đoán</h2>
          <p>
            Kiểm tra xem tệp có khớp bản đã cấp phát và hồ sơ chữ ký có hợp lệ
            hay không.
          </p>
          <p>
            Không khớp không đồng nghĩa với giả mạo. Kết quả chưa đủ bằng chứng
            sẽ được nói rõ.
          </p>
          <details className="guide-details">
            <summary>Phạm vi kiểm tra</summary>
            <p>
              Bản Integrity Release đối chiếu chính xác tệp đã cấp phát. Nhận
              diện sau chỉnh sửa hoặc chuyển đổi định dạng chưa khả dụng.
            </p>
            <p>
              Dữ liệu kỹ thuật có trong hồ sơ kết quả, không phải kết luận pháp
              lý.
            </p>
          </details>
        </aside>
      </div>
    </main>
  );
}
