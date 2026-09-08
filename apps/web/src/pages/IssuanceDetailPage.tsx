import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Download, ExternalLink, FileCheck, FileSpreadsheet, Loader2, Shield } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { CompactIdentifier } from "../components/CompactIdentifier";
import {
  getIssuance,
  getIssuanceResult,
  IssuanceResultUnavailableError,
  openIssuanceResult,
} from "../features/issuances/issuances";
import { JOB_LABELS } from "../features/jobs/useJob";

export function IssuanceDetailPage() {
  const { id } = useParams();
  const queryClient = useQueryClient();
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
    onError: async (error) => {
      if (error instanceof IssuanceResultUnavailableError) {
        await queryClient.invalidateQueries({ queryKey: ["issuance", id] });
      }
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
        <div className="page-heading-badge">
          <FileCheck size={14} aria-hidden="true" />
          <span>Hồ sơ chứng nhận</span>
        </div>
        <h1>Hồ sơ cấp phát</h1>
        <p>Thông tin và bản PDF đã tạo cho lần cấp phát này.</p>
      </header>

      {issuance.isPending ? (
        <section className="status-board" aria-busy="true">
          <div className="board-loading">
            <Loader2 className="spinner" size={24} aria-hidden="true" />
            <p>Đang tải hồ sơ</p>
          </div>
        </section>
      ) : null}

      {issuance.error ? <p className="form-error" role="alert">{issuance.error.message}</p> : null}

      {issuance.data ? (
        <section className="status-board issuance-record">
          <div className="record-header">
            <div className="record-icon" aria-hidden="true">
              <Shield size={22} strokeWidth={2} />
            </div>
            <div className="record-meta">
              <h2>Chứng thư cấp phát cá nhân hóa</h2>
              <p className="record-sub">Tài liệu đã được ký số Ed25519 và nhúng thủy vân bảo mật.</p>
            </div>
          </div>

          <dl className="status-details">
            <div>
              <dt>Mã hồ sơ</dt>
              <dd><CompactIdentifier label="Mã hồ sơ" value={issuance.data.id} /></dd>
            </div>
            <div>
              <dt>Trạng thái</dt>
              <dd>
                <span className="status-pill" data-status={issuance.data.status ?? undefined}>
                  {issuance.data.status ? JOB_LABELS[issuance.data.status] ?? issuance.data.status : "Chưa có"}
                </span>
              </dd>
            </div>
            <div>
              <dt>Thời điểm tạo</dt>
              <dd>
                <time dateTime={issuance.data.issued_at}>
                  {new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(issuance.data.issued_at))}
                </time>
              </dd>
            </div>
            {issuance.data.algorithm_label ? (
              <div>
                <dt>Mức độ thuật toán</dt>
                <dd><span className="algo-badge">Thử nghiệm — chưa phát hành</span></dd>
              </div>
            ) : null}
          </dl>

          <div className="record-links">
            {issuance.data.job_id ? (
              <Link className="button button-secondary" to={`/jobs/${issuance.data.job_id}`}>
                <span>Xem tiến độ xử lý</span>
                <ExternalLink size={15} aria-hidden="true" />
              </Link>
            ) : null}
          </div>

          {issuance.data.result_available ? (
            <div className="result-actions" aria-live="polite">
              <button
                className="button button-primary result-download"
                type="button"
                data-state={download.isPending ? "loading" : download.isError ? "error" : download.isSuccess ? "success" : "default"}
                disabled={download.isPending}
                onClick={() => download.mutate()}
              >
                {download.isPending ? <Loader2 className="spinner" size={18} aria-hidden="true" /> : <Download size={18} aria-hidden="true" />}
                <span>{downloadLabel}</span>
              </button>
              {download.isError ? <p className="form-error" role="alert">{download.error.message}</p> : null}
            </div>
          ) : processing ? (
            <div className="result-notice notice-processing">
              <Loader2 className="spinner" size={18} aria-hidden="true" />
              <p className="result-note">Kết quả PDF đang được xử lý.</p>
            </div>
          ) : (
            <div className="result-notice notice-unavailable">
              <p className="result-note">Kết quả PDF hiện không có sẵn. Hãy kiểm tra trạng thái công việc hoặc chạy lại quy trình demo.</p>
            </div>
          )}
        </section>
      ) : null}
    </main>
  );
}
