import { useEffect, useRef, useState } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ArrowRight, Check, Clock3 } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";
import { CompactIdentifier } from "../components/CompactIdentifier";
import { StatusBadge } from "../components/StatusBadge";
import {
  JOB_LABELS,
  TERMINAL_JOB_STATUSES,
  useJob,
} from "../features/jobs/useJob";
import { describeJobError } from "../features/shared/jobErrors";
gsap.registerPlugin(useGSAP);
export function JobDetailPage() {
  const { id } = useParams();
  const location = useLocation();
  const root = useRef<HTMLElement>(null);
  const state = location.state as {
    issuanceId?: string;
    verificationId?: string;
  } | null;
  const job = useJob(id ?? null);
  const data = job.data;
  const done = data?.status === "succeeded";
  const terminal = Boolean(data && TERMINAL_JOB_STATUSES.has(data.status));
  const failed = terminal && !done;
  const [elapsed, setElapsed] = useState(0);

  useEffect(() => {
    if (data?.created_at && !terminal) {
      const diff = Math.floor(
        (Date.now() - new Date(data.created_at).getTime()) / 1000,
      );
      if (diff > 0 && diff < 3600) {
        setElapsed(diff);
      }
    }
  }, [data?.created_at, terminal]);

  useEffect(() => {
    if (terminal) return;
    const timer = setInterval(() => {
      setElapsed((prev) => prev + 1);
    }, 1000);
    return () => clearInterval(timer);
  }, [terminal]);

  const durationSeconds =
    data?.created_at && data?.updated_at
      ? Math.max(
          1,
          Math.round(
            (new Date(data.updated_at).getTime() -
              new Date(data.created_at).getTime()) /
              1000,
          ),
        )
      : null;
  const verification =
    data?.kind === "verification" ||
    Boolean(state?.verificationId ?? data?.verification_id);
  const resultId = verification
    ? (state?.verificationId ?? data?.verification_id)
    : (state?.issuanceId ?? data?.issuance_id);
  const stage =
    data?.status === "created"
      ? 0
      : data?.status === "queued" || data?.status === "retryable_failed"
        ? 1
        : done
          ? 3
          : 2;
  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function" || !data) return;
      const media = gsap.matchMedia();
      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          ".job-current",
          { opacity: 0.5, y: 3 },
          {
            opacity: 1,
            y: 0,
            duration: 0.22,
            clearProps: "all",
            ease: "power2.out",
          },
        );
      });
      return () => media.revert();
    },
    { scope: root, dependencies: [data?.status], revertOnUpdate: true },
  );
  const explanation = done
    ? "Kết quả đã sẵn sàng. Mở hồ sơ để xem và tiếp tục."
    : failed
      ? data?.status === "cancelled"
        ? "Công việc đã bị hủy. Chưa có kết luận về tài liệu."
        : "Hệ thống chưa hoàn tất xử lý. Xem mã lỗi bên dưới hoặc thử lại với tệp nguồn."
      : data?.status === "retryable_failed"
        ? "Có gián đoạn tạm thời. Hệ thống sẽ tự động thử lại; bạn không cần gửi thêm yêu cầu."
        : data?.status === "processing"
          ? verification
            ? "Đang kiểm tra tài liệu và tổng hợp bằng chứng."
            : "Đang tạo bản PDF và hồ sơ cấp phát có chữ ký."
          : "Yêu cầu đã được tiếp nhận và đang chờ xử lý.";
  return (
    <main ref={root} className="workspace-page result-page">
      <header className="page-heading" data-motion-block>
        <p className="page-context">
          {verification ? "Xác minh tài liệu" : "Cấp phát tài liệu"}
        </p>
        <h1>Tiến độ xử lý</h1>
        <p>Trạng thái sẽ tự động cập nhật cho đến khi hoàn tất.</p>
      </header>
      {job.isPending ? (
        <p className="loading-state" role="status">
          Đang tải trạng thái
        </p>
      ) : job.error ? (
        <div className="error-callout" role="alert">
          <h2>Không thể tải thông tin công việc</h2>
          <p>{job.error.message}</p>
          <button
            className="button button-secondary"
            onClick={() => void job.refetch()}
          >
            Thử lại
          </button>
        </div>
      ) : data ? (
        <>
          <section className="status-board job-record">
            <div className="job-current" aria-live="polite" data-motion-block>
              <StatusBadge
                label="Trạng thái công việc"
                status={data.status}
                title={JOB_LABELS[data.status] ?? data.status}
              />
              <p>{explanation}</p>
            </div>
            <ol className="job-steps" aria-label="Tiến trình các bước" data-motion-block>
              {[
                "Tiếp nhận",
                "Hàng đợi",
                verification ? "Kiểm tra" : "Tạo bản cấp phát",
                "Hoàn tất",
              ].map((label, index) => (
                <li
                  key={label}
                  data-state={
                    done || index < stage
                      ? "done"
                      : index === stage
                        ? failed
                          ? "failed"
                          : "current"
                        : "waiting"
                  }
                  aria-current={index === stage ? "step" : undefined}
                >
                  <span className="step-marker" aria-hidden="true">
                    {done || index < stage ? <Check size={15} /> : index + 1}
                  </span>
                  <span>{label}</span>
                </li>
              ))}
            </ol>
            {!terminal ? (
              <p className="waiting-note" aria-live="polite">
                <Clock3 size={18} aria-hidden="true" />
                {elapsed <= 15
                  ? `Đã xử lý: ${elapsed}s · Trang tự cập nhật khi có kết quả.`
                  : `Đang xử lý trong hàng đợi (${elapsed}s) · Vui lòng giữ nguyên trang...`}
              </p>
            ) : done && durationSeconds !== null ? (
              <p className="waiting-note success-note">
                <Clock3 size={18} aria-hidden="true" />
                Đã hoàn tất sau {durationSeconds} giây.
              </p>
            ) : null}
            {data.safe_error_code ? (
              <p className="form-error" role="alert">
                {describeJobError(data.safe_error_code)}
                <span className="field-code">{data.safe_error_code}</span>
              </p>
            ) : null}
            <div className="job-actions">
              {resultId ? (
                <Link
                  className={
                    done ? "button button-primary" : "button button-secondary"
                  }
                  to={`/${verification ? "verifications" : "issuances"}/${resultId}`}
                >
                  {verification ? "Mở hồ sơ kiểm chứng" : "Mở hồ sơ cấp phát"}
                  <ArrowRight size={16} aria-hidden="true" />
                </Link>
              ) : null}
              {failed ? (
                <Link
                  className="button button-secondary"
                  to={verification ? "/verify" : "/issue"}
                >
                  Chọn tệp và thử lại
                </Link>
              ) : null}
            </div>
          </section>
          <section className="record-metadata" data-motion-block>
            <h2>Thông tin công việc</h2>
            <dl className="status-details">
              <div>
                <dt>Mã công việc</dt>
                <dd>
                  <CompactIdentifier label="Mã công việc" value={data.id} full />
                </dd>
              </div>
              <div>
                <dt>Lần xử lý</dt>
                <dd>Lần {data.attempt + 1}</dd>
              </div>
              {durationSeconds !== null ? (
                <div>
                  <dt>Thời gian xử lý</dt>
                  <dd>{durationSeconds} giây</dd>
                </div>
              ) : null}
              <div>
                <dt>Cập nhật từ hệ thống</dt>
                <dd>
                  <time dateTime={data.updated_at}>
                    {new Intl.DateTimeFormat("vi-VN", {
                      dateStyle: "medium",
                      timeStyle: "short",
                    }).format(new Date(data.updated_at))}
                  </time>
                </dd>
              </div>
            </dl>
          </section>
        </>
      ) : null}
    </main>
  );
}
