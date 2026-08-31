import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { canViewVerification, useSession } from "../features/auth/session";
import { EvidenceSummary } from "../features/evidence/EvidenceSummary";
import { STATUS_COPY } from "../features/evidence/copy";
import { JOB_LABELS } from "../features/jobs/useJob";
import { getVerification } from "../features/verifications/verifications";

function missingEvidenceCopy(jobStatus: string | null): string {
  if (jobStatus === "failed" || jobStatus === "dead_lettered") {
    return "Công việc xử lý thất bại nên không có bằng chứng kiểm chứng.";
  }
  if (jobStatus === "cancelled") return "Công việc đã bị hủy nên không có kết quả kiểm chứng.";
  if (jobStatus === "succeeded") {
    return "Công việc đã hoàn tất nhưng API chưa cung cấp kết quả kiểm chứng; giao diện không tự suy luận kết quả.";
  }
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

  if (!permitted) {
    return (
      <main className="workspace-page">
        <header className="page-heading"><h1>Không có quyền xem kiểm chứng</h1><p>Phiên hiện tại không được phép đọc hồ sơ kiểm chứng.</p></header>
      </main>
    );
  }

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <h1>Kết quả kiểm chứng</h1>
        <p>Bằng chứng kỹ thuật được trình bày tách biệt với giới hạn và suy luận để tránh khẳng định quá mức.</p>
      </header>
      {verification.isPending ? <section className="status-board" aria-busy="true"><p>Đang tải hồ sơ kiểm chứng</p></section> : null}
      {verification.error ? <p className="form-error" role="alert">{verification.error.message}</p> : null}
      {verification.data ? (
        <>
          <section className="status-board">
            <div className="status-primary" data-status={verification.data.job_status ?? undefined}>
              <span className="status-dot" aria-hidden="true" />
              <div>
                <p>Trạng thái kết quả</p>
                <h2>{verification.data.status ? STATUS_COPY[verification.data.status].label : verification.data.job_status ? JOB_LABELS[verification.data.job_status] : "Chưa có công việc"}</h2>
              </div>
            </div>
            <dl className="status-details">
              <div><dt>Mã kiểm chứng</dt><dd>{verification.data.id}</dd></div>
              <div><dt>Công việc</dt><dd>{verification.data.job_status ? JOB_LABELS[verification.data.job_status] : "Chưa có"}</dd></div>
              <div><dt>Thời điểm tạo</dt><dd>{new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(verification.data.created_at))}</dd></div>
            </dl>
            {verification.data.job_id ? <Link className="button button-secondary" to={`/jobs/${verification.data.job_id}`}>Xem tiến độ xử lý</Link> : null}
          </section>
          {verification.data.status ? <EvidenceSummary status={verification.data.status} evidence={verification.data.evidence} /> : (
            <p className="result-note">{missingEvidenceCopy(verification.data.job_status)}</p>
          )}
        </>
      ) : null}
    </main>
  );
}
