import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Check, Download, ArrowRight } from "lucide-react";
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

  const processing =
    issuance.data?.status &&
    !["succeeded", "failed", "dead_lettered", "cancelled"].includes(
      issuance.data.status,
    );
  const isCompleted = issuance.data?.status === "succeeded";
  const available = Boolean(issuance.data?.result_available);

  const downloadLabel = download.isPending
    ? "Đang tạo liên kết"
    : download.isError
      ? "Thử tải lại"
      : download.isSuccess
        ? "Đã mở bản tải"
        : "Tải PDF kết quả";

  return (
    <main className="workspace-page result-page">
      <header className="page-heading">
        <p className="page-context">Cấp phát tài liệu</p>
        <h1>Hồ sơ cấp phát</h1>
      </header>
      {issuance.isPending ? (
        <p className="loading-state" role="status">
          Đang tải hồ sơ
        </p>
      ) : null}
      {issuance.error ? (
        <div className="error-callout" role="alert">
          <p>{issuance.error.message}</p>
          <button
            className="button button-secondary"
            onClick={() => void issuance.refetch()}
          >
            Thử lại
          </button>
        </div>
      ) : null}
      {issuance.data ? (
        <>
          <section
            className="verdict"
            data-tone={
              available
                ? "success"
                : processing || isCompleted
                  ? "neutral"
                  : "error"
            }
            aria-label="Kết quả cấp phát"
          >
            <span className="verdict-mark" aria-hidden="true">
              {isCompleted ? <Check size={30} /> : <Download size={30} />}
            </span>
            <div>
              <p className="verdict-label">
                {isCompleted ? "Cấp phát thành công" : "Trạng thái cấp phát"}
              </p>
              <h2>
                {available
                  ? "Bản cấp phát đã sẵn sàng"
                  : isCompleted
                    ? "Đã cấp phát · PDF không khả dụng"
                    : processing
                      ? "Đang chuẩn bị bản cấp phát"
                      : "Chưa có bản cấp phát"}
              </h2>
              <p>
                {available
                  ? "Lưu bản PDF kết quả và gửi đúng tệp này cho người nhận."
                  : "Theo dõi công việc để biết trạng thái và bước tiếp theo."}
              </p>
            </div>
          </section>
          <div className="result-next">
            {issuance.data.result_available ? (
              <button
                className="button button-primary"
                type="button"
                disabled={download.isPending}
                onClick={() => download.mutate()}
              >
                <Download size={18} aria-hidden="true" />
                {downloadLabel}
              </button>
            ) : (
              <p className="result-note">
                {processing
                  ? "Kết quả PDF đang được xử lý."
                  : "Kết quả PDF hiện không có sẵn. Hãy kiểm tra trạng thái công việc hoặc tạo bản cấp phát mới."}
              </p>
            )}
            <Link className="button button-secondary" to="/issue">
              Cấp phát tệp khác
              <ArrowRight size={16} aria-hidden="true" />
            </Link>
          </div>
          {download.isError ? (
            <p className="form-error" role="alert">
              {download.error.message}
            </p>
          ) : null}
          <section className="record-metadata">
            <h2>Thông tin bản cấp phát</h2>
            <dl className="status-details">
              <div>
                <dt>Mã hồ sơ</dt>
                <dd>
                  <CompactIdentifier
                    label="Mã hồ sơ"
                    value={issuance.data.id}
                  />
                </dd>
              </div>
              <div>
                <dt>Trạng thái</dt>
                <dd>
                  {issuance.data.status
                    ? (JOB_LABELS[issuance.data.status] ?? issuance.data.status)
                    : "Chưa có"}
                </dd>
              </div>
              <div>
                <dt>Thời điểm tạo</dt>
                <dd>
                  <time dateTime={issuance.data.issued_at}>
                    {new Intl.DateTimeFormat("vi-VN", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(issuance.data.issued_at))}
                  </time>
                </dd>
              </div>
              {issuance.data.algorithm_label ? (
                <div>
                  <dt>Phương thức</dt>
                  <dd>
                    {issuance.data.algorithm_label === "integrity_release_v1"
                      ? "Toàn vẹn tệp · Integrity Release"
                      : "Thử nghiệm — chưa phát hành"}
                  </dd>
                </div>
              ) : null}
            </dl>
            {issuance.data.job_id ? (
              <Link className="text-link" to={`/jobs/${issuance.data.job_id}`}>
                Xem tiến độ xử lý
              </Link>
            ) : null}
          </section>
        </>
      ) : null}
    </main>
  );
}
