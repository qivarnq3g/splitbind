import { useQuery } from "@tanstack/react-query";
import { AlertCircle, ArrowRight, Check, ShieldAlert } from "lucide-react";
import { Link, useParams } from "react-router-dom";
import { CompactIdentifier } from "../components/CompactIdentifier";
import { canViewVerification, useSession } from "../features/auth/session";
import { EvidenceSummary } from "../features/evidence/EvidenceSummary";
import {
  verificationCopy,
  isIntegrityNonExact,
} from "../features/evidence/copy";
import { JOB_LABELS } from "../features/jobs/useJob";
import { getVerification } from "../features/verifications/verifications";

function missingEvidenceCopy(status: string | null): string {
  if (status === "failed" || status === "dead_lettered")
    return "Công việc xử lý thất bại nên không có bằng chứng kiểm chứng.";
  if (status === "cancelled")
    return "Công việc đã bị hủy nên không có kết quả kiểm chứng.";
  if (status === "succeeded")
    return "Công việc đã hoàn tất nhưng API chưa cung cấp kết quả kiểm chứng; giao diện không tự suy luận kết quả.";
  return "Bằng chứng chưa sẵn sàng trong khi công việc đang được xử lý.";
}
export function VerificationDetailPage() {
  const { id } = useParams();
  const session = useSession();
  const permitted = canViewVerification(session.data?.user?.role);
  const verification = useQuery({
    queryKey: ["verification", id],
    queryFn: ({ signal }) => getVerification(id!, signal),
    enabled: Boolean(id) && permitted,
  });
  if (!permitted)
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Không có quyền xem kiểm chứng</h1>
          <p>Phiên hiện tại không được phép đọc hồ sơ kiểm chứng.</p>
        </header>
        <Link className="button button-secondary" to="/">
          Về trang làm việc
        </Link>
      </main>
    );
  const data = verification.data;
  const copy = data?.status
    ? verificationCopy(
        data.status,
        data.evidence.algorithm_label,
        data.evidence.exact_file_hash_match,
      )
    : null;
  const nonExact =
    data &&
    isIntegrityNonExact(
      data.evidence.algorithm_label,
      data.evidence.exact_file_hash_match,
    );
  const tone =
    data?.status === "PROCESSING_FAILED" || data?.status === "INVALID_MANIFEST"
      ? "error"
      : nonExact
        ? "warning"
        : data?.status === "VERIFIED_INTACT"
          ? "success"
          : "warning";
  return (
    <main className="workspace-page result-page">
      <header className="page-heading">
        <p className="page-context">Xác minh tài liệu</p>
        <h1>Kết quả kiểm chứng</h1>
      </header>
      {verification.isPending ? (
        <p className="loading-state" role="status">
          Đang tải hồ sơ kiểm chứng
        </p>
      ) : null}
      {verification.error ? (
        <div className="error-callout" role="alert">
          <p>{verification.error.message}</p>
          <button
            className="button button-secondary"
            onClick={() => void verification.refetch()}
          >
            Thử lại
          </button>
        </div>
      ) : null}
      {data ? (
        <>
          {data.status && copy ? (
            <>
              <section
                className="verdict"
                data-tone={tone}
                aria-label="Kết luận kiểm chứng"
              >
                <span className="verdict-mark" aria-hidden="true">
                  {tone === "success" ? (
                    <Check size={30} />
                  ) : tone === "error" ? (
                    <ShieldAlert size={30} />
                  ) : (
                    <AlertCircle size={30} />
                  )}
                </span>
                <div>
                  <p className="verdict-label">
                    {tone === "success"
                      ? "Đã xác minh"
                      : tone === "error"
                        ? "Không thể xác minh"
                        : "Cần xem xét"}
                  </p>
                  <h2>{copy.label}</h2>
                  <p>{copy.inference}</p>
                </div>
              </section>
              <div className="result-next">
                <Link className="button button-secondary" to="/verify">
                  Kiểm tra tệp khác
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
                <p>
                  Kết quả không xác định ai đã chỉnh sửa hoặc phát tán tài liệu.
                </p>
              </div>
              <EvidenceSummary
                status={data.status}
                evidence={data.evidence}
                showConclusion={false}
              />
            </>
          ) : (
            <section className="status-board">
              <h2>Chưa có kết luận</h2>
              <p>{missingEvidenceCopy(data.job_status)}</p>
            </section>
          )}
          <section className="record-metadata" aria-label="Thông tin hồ sơ">
            <h2>Hồ sơ kiểm chứng</h2>
            <dl className="status-details">
              <div>
                <dt>Mã kiểm chứng</dt>
                <dd>
                  <CompactIdentifier label="Mã kiểm chứng" value={data.id} />
                </dd>
              </div>
              <div>
                <dt>Công việc</dt>
                <dd>
                  {data.job_status ? JOB_LABELS[data.job_status] : "Chưa có"}
                </dd>
              </div>
              <div>
                <dt>Thời điểm tạo</dt>
                <dd>
                  <time dateTime={data.created_at}>
                    {new Intl.DateTimeFormat("vi-VN", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(data.created_at))}
                  </time>
                </dd>
              </div>
            </dl>
            {data.job_id ? (
              <Link className="text-link" to={`/jobs/${data.job_id}`}>
                Xem tiến độ xử lý
              </Link>
            ) : null}
          </section>
        </>
      ) : null}
    </main>
  );
}
