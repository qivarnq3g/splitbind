import { useState } from "react";
import { ArrowRight, Clock3, FileKey2, History as HistoryIcon, ScanSearch } from "lucide-react";
import { Link } from "react-router-dom";
import { CompactIdentifier } from "../components/CompactIdentifier";
import { STATUS_COPY } from "../features/evidence/copy";
import { JOB_LABELS } from "../features/jobs/useJob";
import { useJobList } from "../features/jobs/useJobList";
import { describeJobError } from "../features/shared/jobErrors";

export function HistoryPage() {
  const [kindFilter, setKindFilter] = useState<"issuance" | "verification" | null>(null);
  const jobs = useJobList(kindFilter);

  return (
    <main className="workspace-page history-page">
      <header className="page-heading">
        <p className="page-context">Quản lý tài liệu</p>
        <h1>Lịch sử xử lý</h1>
        <p>Danh sách các bản cấp phát và kiểm chứng được lưu trữ trong hệ thống.</p>
      </header>

      <div className="history-filter-bar" role="tablist" aria-label="Bộ lọc công việc">
        <button
          type="button"
          role="tab"
          aria-selected={kindFilter === null}
          className={`filter-tab ${kindFilter === null ? "active" : ""}`}
          onClick={() => setKindFilter(null)}
        >
          Tất cả
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={kindFilter === "issuance"}
          className={`filter-tab ${kindFilter === "issuance" ? "active" : ""}`}
          onClick={() => setKindFilter("issuance")}
        >
          <FileKey2 size={16} aria-hidden="true" />
          Cấp phát tài liệu
        </button>
        <button
          type="button"
          role="tab"
          aria-selected={kindFilter === "verification"}
          className={`filter-tab ${kindFilter === "verification" ? "active" : ""}`}
          onClick={() => setKindFilter("verification")}
        >
          <ScanSearch size={16} aria-hidden="true" />
          Xác minh tài liệu
        </button>
      </div>

      {jobs.isPending ? (
        <p className="loading-state" role="status">
          Đang tải lịch sử công việc...
        </p>
      ) : jobs.error ? (
        <div className="error-callout" role="alert">
          <h2>Không thể tải lịch sử</h2>
          <p>{jobs.error.message}</p>
          <button
            className="button button-secondary"
            type="button"
            onClick={() => void jobs.refetch()}
          >
            Thử lại
          </button>
        </div>
      ) : jobs.data && jobs.data.length === 0 ? (
        <div className="empty-history" role="status">
          <HistoryIcon size={40} aria-hidden="true" className="empty-icon" />
          <h2>Chưa có công việc nào</h2>
          <p>
            {kindFilter === "issuance"
              ? "Bạn chưa thực hiện yêu cầu cấp phát nào."
              : kindFilter === "verification"
                ? "Bạn chưa thực hiện yêu cầu kiểm chứng nào."
                : "Hệ thống chưa ghi nhận công việc cấp phát hoặc kiểm chứng nào."}
          </p>
          <div className="empty-actions">
            <Link to="/issue" className="button button-primary">
              <FileKey2 size={16} aria-hidden="true" />
              Cấp phát tài liệu mới
            </Link>
            <Link to="/verify" className="button button-secondary">
              <ScanSearch size={16} aria-hidden="true" />
              Xác minh tài liệu
            </Link>
          </div>
        </div>
      ) : (
        <div className="history-list" role="feed" aria-label="Danh sách công việc">
          {jobs.data?.map((item) => {
            const isIssuance = item.kind === "issuance";
            const resultId = isIssuance ? item.issuance_id : item.verification_id;
            const isDone = item.status === "succeeded";

            return (
              <article key={item.id} className="history-card" data-motion-block aria-labelledby={`job-title-${item.id}`}>
                <div className="history-card-header">
                  <div className="history-card-tags">
                    <span className={`kind-badge ${item.kind}`}>
                      {isIssuance ? "Cấp phát" : "Xác minh"}
                    </span>
                    <span className="status-badge-inline" data-status={item.status}>
                      <span className="status-dot" aria-hidden="true" />
                      {JOB_LABELS[item.status] ?? item.status}
                    </span>
                    {item.verification_status ? (
                      <span className="vstatus-badge" data-vstatus={item.verification_status}>
                        {STATUS_COPY[item.verification_status as keyof typeof STATUS_COPY]?.label ??
                          item.verification_status}
                      </span>
                    ) : null}
                  </div>
                  <time className="history-card-time" dateTime={item.created_at}>
                    <Clock3 size={14} aria-hidden="true" />
                    {new Intl.DateTimeFormat("vi-VN", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(item.created_at))}
                  </time>
                </div>

                <div className="history-card-details">
                  <div className="history-field">
                    <span className="field-title">Mã công việc:</span>
                    <CompactIdentifier label="Mã công việc" value={item.id} full />
                  </div>
                  {item.recipient_email ? (
                    <div className="history-field">
                      <span className="field-title">Người nhận:</span>
                      <span className="field-value">
                        <strong>{item.recipient_email}</strong>
                        {item.recipient_name ? ` (${item.recipient_name})` : ""}
                      </span>
                    </div>
                  ) : null}
                  {item.safe_error_code ? (
                    <div className="history-field history-field-error">
                      <span className="field-title">Lý do:</span>
                      <span className="field-error">
                        {describeJobError(item.safe_error_code)}
                        <span className="field-code">{item.safe_error_code}</span>
                      </span>
                    </div>
                  ) : null}
                </div>

                <div className="history-card-actions">
                  <Link to={`/jobs/${item.id}`} className="button button-secondary">
                    Xem tiến độ
                  </Link>
                  {isDone && resultId ? (
                    <Link
                      to={`/${isIssuance ? "issuances" : "verifications"}/${resultId}`}
                      className="button button-primary"
                    >
                      {isIssuance ? "Mở hồ sơ cấp phát" : "Mở hồ sơ kiểm chứng"}
                      <ArrowRight size={15} aria-hidden="true" />
                    </Link>
                  ) : null}
                </div>
              </article>
            );
          })}
        </div>
      )}
    </main>
  );
}
