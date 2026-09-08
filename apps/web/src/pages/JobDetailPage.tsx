import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Activity, ArrowRight, Check, CheckCircle2, Clock, Loader2, ShieldCheck, XCircle } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import { CompactIdentifier } from "../components/CompactIdentifier";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { JOB_LABELS, useJob } from "../features/jobs/useJob";

gsap.registerPlugin(useGSAP);

const LIFECYCLE_STEPS = [
  { key: "created", label: "Tiếp nhận" },
  { key: "queued", label: "Hàng đợi" },
  { key: "processing", label: "Xử lý thuật toán" },
  { key: "succeeded", label: "Hoàn tất" },
] as const;

function getStepIndex(status: string | undefined): number {
  if (!status) return 0;
  if (status === "created") return 0;
  if (status === "queued") return 1;
  if (status === "processing") return 2;
  if (status === "succeeded") return 3;
  if (status === "failed" || status === "dead_lettered" || status === "cancelled") return 2;
  return 1;
}

export function JobDetailPage() {
  const { id } = useParams();
  const location = useLocation();
  const containerRef = useRef<HTMLElement>(null);
  const workflowState = location.state as { issuanceId?: string; verificationId?: string } | null;
  const issuanceId = workflowState?.issuanceId;
  const verificationId = workflowState?.verificationId;
  const job = useJob(id ?? null);

  const isCompleted = job.data?.status === "succeeded";
  const isFailed = job.data?.status === "failed" || job.data?.status === "dead_lettered";
  const isProcessing = job.data?.status === "processing" || job.data?.status === "queued";
  const currentStep = getStepIndex(job.data?.status);

  useGSAP(
    () => {
      if (typeof window.matchMedia !== "function" || !job.data) return;
      const media = gsap.matchMedia();

      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          ".lifecycle-step",
          { autoAlpha: 0, y: 6 },
          { autoAlpha: 1, y: 0, duration: 0.3, stagger: 0.08, ease: "power2.out", clearProps: "all" }
        );
      });

      return () => media.revert();
    },
    { scope: containerRef, dependencies: [job.data?.status] }
  );

  return (
    <main ref={containerRef} className="workspace-page">
      <header className="page-heading">
        <div className="page-heading-badge">
          <Activity size={14} aria-hidden="true" />
          <span>Hàng đợi hệ thống</span>
        </div>
        <h1>Tiến độ xử lý</h1>
        <p>Trạng thái sẽ tự động cập nhật cho đến khi hoàn tất.</p>
      </header>

      {job.isPending ? (
        <section className="status-board" aria-busy="true">
          <div className="board-loading">
            <Loader2 className="spinner" size={24} aria-hidden="true" />
            <p>Đang tải trạng thái</p>
          </div>
        </section>
      ) : job.error ? (
        <section className="status-board">
          <EmptyState
            icon={<XCircle size={32} className="text-error" />}
            title="Không thể tải thông tin công việc"
            description={job.error.message}
          />
        </section>
      ) : job.data ? (
        <section className="status-board job-record" aria-live="polite">
          <div className="job-record-top">
            <StatusBadge
              label="Trạng thái công việc"
              status={job.data.status}
              title={JOB_LABELS[job.data.status] ?? job.data.status}
            />
            <div className="job-pulse-indicator" data-status={job.data.status} aria-hidden="true">
              {isProcessing ? <span className="pulse-ring" /> : null}
              {isCompleted ? <CheckCircle2 size={24} className="icon-success" /> : null}
              {isFailed ? <XCircle size={24} className="icon-error" /> : null}
            </div>
          </div>

          <div className="job-lifecycle-track" aria-label="Tiến trình các bước" role="list">
            {LIFECYCLE_STEPS.map((step, idx) => {
              const isDone = isCompleted || idx < currentStep;
              const isCurrent = idx === currentStep && !isCompleted && !isFailed;
              const isStepFailed = isFailed && idx === currentStep;

              return (
                <div
                  key={step.key}
                  className={`lifecycle-step ${isDone ? "is-done" : ""} ${isCurrent ? "is-active" : ""} ${isStepFailed ? "is-failed" : ""}`.trim()}
                  role="listitem"
                >
                  <div className="step-marker" aria-hidden="true">
                    {isDone ? <Check size={13} strokeWidth={2.5} /> : <span>{idx + 1}</span>}
                  </div>
                  <span className="step-label">{step.label}</span>
                </div>
              );
            })}
          </div>

          <dl className="status-details">
            <div>
              <dt>Mã công việc</dt>
              <dd><CompactIdentifier label="Mã công việc" value={job.data.id} /></dd>
            </div>
            <div>
              <dt>Lần xử lý</dt>
              <dd>
                <span className="attempt-badge">Lần {job.data.attempt + 1}</span>
              </dd>
            </div>
            <div>
              <dt>Cập nhật</dt>
              <dd>
                <time dateTime={job.data.updated_at}>
                  {new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(job.data.updated_at))}
                </time>
              </dd>
            </div>
          </dl>

          {job.data.safe_error_code ? (
            <div className="error-callout" role="alert">
              <p className="form-error">Mã lỗi an toàn: {job.data.safe_error_code}</p>
            </div>
          ) : null}

          <div className="job-actions">
            {(issuanceId ?? job.data.issuance_id) ? (
              <Link className="button button-secondary" to={`/issuances/${issuanceId ?? job.data.issuance_id}`}>
                <span>Mở hồ sơ cấp phát</span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            ) : null}
            {(verificationId ?? job.data.verification_id) ? (
              <Link className="button button-secondary" to={`/verifications/${verificationId ?? job.data.verification_id}`}>
                <span>Mở hồ sơ kiểm chứng</span>
                <ArrowRight size={16} aria-hidden="true" />
              </Link>
            ) : null}
          </div>
        </section>
      ) : null}
    </main>
  );
}
