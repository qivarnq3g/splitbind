import { useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getIssuance } from "../features/issuances/issuances";
import { JOB_LABELS } from "../features/jobs/useJob";

export function IssuanceDetailPage() {
  const { id } = useParams();
  const issuance = useQuery({
    queryKey: ["issuance", id],
    queryFn: ({ signal }) => getIssuance(id!, signal),
    enabled: Boolean(id),
  });

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <h1>Hồ sơ cấp phát</h1>
        <p>Thông tin được giới hạn theo tổ chức và vai trò của phiên đăng nhập.</p>
      </header>
      {issuance.isPending ? <section className="status-board" aria-busy="true"><p>Đang tải hồ sơ</p></section> : null}
      {issuance.error ? <p className="form-error" role="alert">{issuance.error.message}</p> : null}
      {issuance.data ? (
        <section className="status-board">
          <dl className="status-details">
            <div><dt>Mã hồ sơ</dt><dd>{issuance.data.id}</dd></div>
            <div><dt>Trạng thái</dt><dd>{issuance.data.status ? JOB_LABELS[issuance.data.status] ?? issuance.data.status : "Chưa có"}</dd></div>
            <div><dt>Thời điểm tạo</dt><dd>{new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(issuance.data.issued_at))}</dd></div>
          </dl>
          {issuance.data.job_id ? <Link className="button button-secondary" to={`/jobs/${issuance.data.job_id}`}>Xem tiến độ xử lý</Link> : null}
          <p className="result-note">API hiện tại chưa cung cấp URL tải kết quả. Giao diện không tạo hoặc suy đoán liên kết tải xuống.</p>
        </section>
      ) : null}
    </main>
  );
}
