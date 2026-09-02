import { useMutation, useQuery } from "@tanstack/react-query";
import { Link, useParams } from "react-router-dom";

import { getIssuance, getIssuanceResult, openIssuanceResult } from "../features/issuances/issuances";
import { JOB_LABELS } from "../features/jobs/useJob";

export function IssuanceDetailPage() {
  const { id } = useParams();
  const issuance = useQuery({
    queryKey: ["issuance", id],
    queryFn: ({ signal }) => getIssuance(id!, signal),
    enabled: Boolean(id),
  });
  const download = useMutation({
    mutationFn: async () => {
      const result = await getIssuanceResult(id!);
      openIssuanceResult(result.download_url);
    },
  });

  const processing = issuance.data?.status && ![
    "succeeded",
    "failed",
    "dead_lettered",
    "cancelled",
  ].includes(issuance.data.status);
  const downloadLabel = download.isPending
    ? "Đang tạo liên kết"
    : download.isError
      ? "Thử tải lại"
      : download.isSuccess
        ? "Đã mở bản tải"
        : "Tải PDF kết quả";

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
            {issuance.data.algorithm_label ? <div><dt>Mức độ thuật toán</dt><dd>Thử nghiệm — chưa phát hành</dd></div> : null}
          </dl>
          {issuance.data.job_id ? <Link className="button button-secondary" to={`/jobs/${issuance.data.job_id}`}>Xem tiến độ xử lý</Link> : null}
          {issuance.data.result_available ? (
            <div className="result-actions" aria-live="polite">
              <button
                className="button button-primary result-download"
                type="button"
                data-state={download.isPending ? "loading" : download.isError ? "error" : download.isSuccess ? "success" : "default"}
                disabled={download.isPending}
                onClick={() => download.mutate()}
              >
                {downloadLabel}
              </button>
              {download.isError ? <p className="form-error" role="alert">{download.error.message}</p> : null}
            </div>
          ) : processing ? (
            <p className="result-note">Kết quả PDF đang được xử lý.</p>
          ) : (
            <p className="result-note">Kết quả PDF hiện không có sẵn. Hãy kiểm tra trạng thái công việc hoặc chạy lại quy trình demo.</p>
          )}
        </section>
      ) : null}
    </main>
  );
}
