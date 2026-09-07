import { Link, useLocation, useParams } from "react-router-dom";

import { CompactIdentifier } from "../components/CompactIdentifier";
import { StatusBadge } from "../components/StatusBadge";
import { JOB_LABELS, useJob } from "../features/jobs/useJob";

export function JobDetailPage() {
  const { id } = useParams();
  const location = useLocation();
  const workflowState = location.state as { issuanceId?: string; verificationId?: string } | null;
  const issuanceId = workflowState?.issuanceId;
  const verificationId = workflowState?.verificationId;
  const job = useJob(id ?? null);

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <h1>Tiến độ xử lý</h1>
        <p>Trạng thái sẽ tự động cập nhật cho đến khi hoàn tất.</p>
      </header>
      {job.isPending ? (
        <section className="status-board" aria-busy="true"><p>Đang tải trạng thái</p></section>
      ) : job.error ? (
        <section className="status-board"><p className="form-error" role="alert">{job.error.message}</p></section>
      ) : job.data ? (
        <section className="status-board job-record" aria-live="polite">
          <StatusBadge label="Trạng thái công việc" status={job.data.status} title={JOB_LABELS[job.data.status] ?? job.data.status} />
          <dl className="status-details">
            <div><dt>Mã công việc</dt><dd><CompactIdentifier label="Mã công việc" value={job.data.id} /></dd></div>
            <div><dt>Lần xử lý</dt><dd>{job.data.attempt + 1}</dd></div>
            <div><dt>Cập nhật</dt><dd>{new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(job.data.updated_at))}</dd></div>
          </dl>
          {job.data.safe_error_code ? <p className="form-error" role="alert">Mã lỗi an toàn: {job.data.safe_error_code}</p> : null}
          {(issuanceId ?? job.data.issuance_id) ? (
            <Link className="button button-secondary" to={`/issuances/${issuanceId ?? job.data.issuance_id}`}>Mở hồ sơ cấp phát</Link>
          ) : null}
          {(verificationId ?? job.data.verification_id) ? (
            <Link className="button button-secondary" to={`/verifications/${verificationId ?? job.data.verification_id}`}>Mở hồ sơ kiểm chứng</Link>
          ) : null}
        </section>
      ) : null}
    </main>
  );
}
