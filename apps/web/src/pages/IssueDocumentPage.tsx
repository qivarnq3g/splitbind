import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ArrowRight } from "lucide-react";
import { Link, useNavigate } from "react-router-dom";
import { DocumentFileInput } from "../components/DocumentFileInput";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { canCreateIssuance, useSession } from "../features/auth/session";
import { getDemoCapabilities } from "../features/demo/capabilities";
import { SafeApiError } from "../features/shared/apiError";
import {
  MAX_PDF_LABEL,
  MAX_PDF_PAGES,
  type UploadStage,
  uploadIssuancePdf,
  validateIssuanceFile,
} from "../features/uploads/uploadIssuance";
import { createIssuance } from "../features/issuances/issuances";
import { formatBytes } from "../features/shared/formatBytes";
export function IssueDocumentPage() {
  const session = useSession();
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);
  const [file, setFile] = useState<File | null>(null);
  const [recipientEmail, setRecipientEmail] = useState("");
  const [recipientName, setRecipientName] = useState("");
  const [stage, setStage] = useState<UploadStage | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);
  const capabilities = useQuery({
    queryKey: ["demo-capabilities"],
    queryFn: ({ signal }) => getDemoCapabilities(signal),
    enabled: Boolean(session.data?.user),
    staleTime: 30_000,
    retry: false,
  });
  const capability = capabilities.data;
  const exactOnly =
    capability === undefined
      ? true
      : capability.algorithm_label === "integrity_release_v1"
        ? capability.transformed_attribution_available !== true
        : false;

  useEffect(() => () => abortRef.current?.abort(), []);

  const issuance = useMutation({
    mutationFn: async () => {
      if (!file)
        throw new SafeApiError("Chưa có tệp. Chọn một tệp rồi thử lại.");
      validateIssuanceFile(file, exactOnly);
      const trimmedEmail = recipientEmail.trim();
      if (!trimmedEmail) {
        throw new SafeApiError(
          "Email người nhận chưa đúng. Kiểm tra email rồi thử lại.",
        );
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const upload = await uploadIssuancePdf(
        file,
        setStage,
        controller.signal,
        exactOnly,
      );
      setStage(null);
      return createIssuance(
        upload.uploadId,
        { email: trimmedEmail, name: recipientName.trim() || undefined },
        controller.signal,
      );
    },
    onSuccess: (created) =>
      navigate(`/jobs/${created.job_id}`, {
        state: { issuanceId: created.id },
      }),
    onSettled: () => setStage(null),
  });

  function selectFile(selected: File | undefined) {
    setValidationError(null);
    issuance.reset();
    if (!selected) {
      setFile(null);
      return;
    }
    try {
      validateIssuanceFile(selected, exactOnly);
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
    issuance.mutate();
  }

  const error = validationError ?? issuance.error?.message ?? null;

  if (!canCreateIssuance(session.data?.user?.role))
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Quyền chỉ đọc</h1>
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
      <header className="page-heading" data-motion-block>
        <p className="page-context">Cấp phát tài liệu</p>
        <h1>Tạo bản cấp phát</h1>
        <p>Chọn tài liệu và người nhận để tạo bản cấp phát riêng.</p>
      </header>
      <div className="workbench-layout">
        <section className="workbench" aria-label="Tạo bản cấp phát" data-motion-block>
          <form
            className="form-stack"
            onSubmit={submit}
            aria-busy={issuance.isPending}
          >
            <div
              className="field upload-dropzone"
              data-state={
                validationError ? "error" : file ? "success" : "default"
              }
            >
              <DocumentFileInput
                id="pdf-file"
                label={exactOnly ? "Tệp PDF" : "Tệp tài liệu hoặc ảnh"}
                accept={
                  exactOnly
                    ? "application/pdf,.pdf"
                    : "application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg"
                }
                disabled={issuance.isPending}
                invalid={Boolean(validationError)}
                describedBy="pdf-help"
                filename={file?.name ?? null}
                onChange={selectFile}
              />
              <p
                className={
                  validationError ? "field-help field-help-error" : "field-help"
                }
                id="pdf-help"
              >
                {validationError ??
                  (file
                    ? `${formatBytes(file.size)} · Tệp được chọn trên thiết bị, chưa tải lên.`
                    : exactOnly
                      ? `PDF · tối đa ${MAX_PDF_LABEL} · PDF tối đa ${MAX_PDF_PAGES} trang`
                      : `PDF, PNG hoặc JPEG · tối đa ${MAX_PDF_LABEL} · PDF tối đa ${MAX_PDF_PAGES} trang`)}
              </p>
            </div>
            <fieldset className="field-group">
              <legend>Người nhận</legend>
            <div className="field">
              <label htmlFor="recipient-email">Email người nhận</label>
              <input
                id="recipient-email"
                name="recipient-email"
                type="email"
                autoComplete="email"
                required
                disabled={issuance.isPending}
                aria-describedby="recipient-email-help"
                placeholder="nguyenvana@example.com"
                value={recipientEmail}
                onChange={(event) => setRecipientEmail(event.target.value)}
              />
              <p className="field-help" id="recipient-email-help">
                Nhập email của người sẽ nhận bản cấp phát.
              </p>
            </div>
            <div className="field">
              <label htmlFor="recipient-name">Họ và tên</label>
              <input
                id="recipient-name"
                name="recipient-name"
                type="text"
                autoComplete="name"
                disabled={issuance.isPending}
                aria-describedby="recipient-name-help"
                placeholder="Nguyễn Văn A"
                value={recipientName}
                onChange={(event) => setRecipientName(event.target.value)}
              />
              <p className="field-help" id="recipient-name-help">
                Không bắt buộc. Dùng để dễ nhận biết người nhận trong hồ sơ.
              </p>
            </div>
            </fieldset>
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
                disabled={issuance.isPending || Boolean(validationError)}
                data-state={
                  issuance.isPending ? "loading" : error ? "error" : "default"
                }
              >
                <span>
                  {issuance.isPending
                    ? "Đang tạo bản cấp phát"
                    : "Tạo bản cấp phát"}
                </span>
                <ArrowRight size={18} aria-hidden="true" />
              </button>
              <p>Nhận tệp kết quả sau khi xử lý.</p>
            </div>
          </form>
        </section>
        <aside className="task-guide" aria-label="Thông tin quy trình" data-motion-block>
          <h2>Từ tài liệu đến bản cấp phát</h2>
          <ol className="guide-steps">
            <li>
              <strong>Chọn tài liệu</strong>
              <span>Giữ nguyên tệp gốc trên thiết bị của bạn.</span>
            </li>
            <li>
              <strong>Tạo bản cấp phát</strong>
              <span>
                Hệ thống xử lý tệp và tạo hồ sơ có chữ ký cho người nhận.
              </span>
            </li>
            <li>
              <strong>Tải và lưu bản cấp phát</strong>
              <span>Gửi đúng bản kết quả để có thể xác minh về sau.</span>
            </li>
          </ol>
        </aside>
      </div>
    </main>
  );
}
