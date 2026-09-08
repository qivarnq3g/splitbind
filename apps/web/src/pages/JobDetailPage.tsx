import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { Activity, ArrowRight, Check, CheckCircle2, Loader2, XCircle } from "lucide-react";
import { Link, useLocation, useParams } from "react-router-dom";

import { CompactIdentifier } from "../components/CompactIdentifier";
import { CryptographicMotif, type CryptographicMotifStage } from "../components/CryptographicMotif";
import { EmptyState } from "../components/EmptyState";
import { StatusBadge } from "../components/StatusBadge";
import { JOB_LABELS, useJob } from "../features/jobs/useJob";

gsap.registerPlugin(useGSAP);

const LIFECYCLE_STEPS = [
  { key: "created", label: "Tiếp nhận", hint: "Ghi nhận yêu cầu" },
  { key: "queued", label: "Hàng đợi", hint: "Sẵn sàng xử lý" },
  { key: "processing", label: "Xử lý bảo vệ", hint: "Bảo vệ & Ký số" },
  { key: "succeeded", label: "Hoàn tất", hint: "Niêm phong thành công" },
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

function getMotifStage(status: string | undefined, isVerification: boolean): CryptographicMotifStage {
  if (!status) return "idle";
  if (status === "succeeded") return "sealed";
  if (status === "failed" || status === "dead_lettered" || status === "cancelled") return "tampered";
  if (status === "processing") return isVerification ? "verifying" : "decomposing";
  if (status === "queued") return "hashing";
  if (status === "created") return "idle";
  if (status === "retryable_failed") return "tampered";
  return "idle";
}

function getTelemetryStatusMessage(status: string | undefined, isVerification: boolean): string {
  switch (status) {
    case "created":
      return "Hệ thống đã tiếp nhận yêu cầu và bắt đầu chuẩn bị xử lý.";
    case "queued":
      return "Đang chờ điều phối lượt xử lý trong hệ thống.";
    case "processing":
      return isVerification
        ? "Đang kiểm tra từng lớp nội dung và đối chiếu chữ ký bảo vệ..."
        : "Đang nhúng dấu vết bảo vệ ẩn và tạo chữ ký số cho tài liệu...";
    case "retryable_failed":
      return "Hệ thống gặp gián đoạn tạm thời và đang tự động thử lại.";
    case "succeeded":
      return isVerification
        ? "Kiểm tra hoàn tất. Bằng chứng toàn vẹn đã sẵn sàng để xem."
        : "Tài liệu đã được niêm phong bảo mật và tạo thành công.";
    case "failed":
    case "dead_lettered":
      return "Xử lý không thành công do tệp không đúng định dạng hoặc bị lỗi.";
    case "cancelled":
      return "Quy trình xử lý đã được dừng.";
    default:
      return "Đang theo dõi trạng thái công việc...";
  }
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
  const isFailed = job.data?.status === "failed" || job.data?.status === "dead_lettered" || job.data?.status === "cancelled";
  const isProcessing = job.data?.status === "processing" || job.data?.status === "queued";
  const isVerification = job.data?.kind === "verification" || Boolean(verificationId ?? job.data?.verification_id);
  const currentStep = getStepIndex(job.data?.status);
  const motifStage = getMotifStage(job.data?.status, isVerification);

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function" || !job.data) {
        return;
      }

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(
          ".lifecycle-step, .pipeline-flow-beam, .node-active-ring, .telemetry-pulse-dot",
          { clearProps: "all" }
        );
        return;
      }

      gsap.fromTo(
        ".lifecycle-step",
        { autoAlpha: 0.7, y: 4 },
        { autoAlpha: 1, y: 0, duration: 0.35, stagger: 0.06, ease: "power2.out", clearProps: "transform,opacity,visibility" }
      );

      if (job.data.status === "processing" || job.data.status === "queued") {
        gsap.to(".pipeline-flow-beam", {
          xPercent: 120,
          duration: 1.6,
          ease: "power1.inOut",
          repeat: -1,
        });

        gsap.to(".node-active-ring", {
          scale: 1.3,
          opacity: 0.25,
          duration: 1.4,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
        });

        gsap.to(".telemetry-pulse-dot", {
          opacity: 0.3,
          scale: 0.8,
          duration: 0.9,
          ease: "sine.inOut",
          repeat: -1,
          yoyo: true,
        });
      } else {
        gsap.set(".pipeline-flow-beam, .node-active-ring, .telemetry-pulse-dot", { clearProps: "all" });
      }
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

          <div className="job-spatial-pipeline">
            <div className="job-chamber">
              <div className="job-chamber-stage" data-stage={motifStage}>
                <CryptographicMotif stage={motifStage} size={120} className="job-stage-motif" />
                <div className="job-chamber-reticle" aria-hidden="true">
                  <span className="chamber-reticle-corner corner-tl" />
                  <span className="chamber-reticle-corner corner-tr" />
                  <span className="chamber-reticle-corner corner-bl" />
                  <span className="chamber-reticle-corner corner-br" />
                </div>
              </div>
              <div className="job-chamber-telemetry">
                <div className="job-telemetry-badge">
                  <span className="telemetry-badge-dot" data-status={job.data.status} />
                  <span className="telemetry-badge-type">
                    {isVerification ? "Kênh kiểm chứng tài liệu" : "Kênh cấp phát tài liệu"}
                  </span>
                </div>
                <p className="job-telemetry-description">
                  {getTelemetryStatusMessage(job.data.status, isVerification)}
                </p>
                {isProcessing ? (
                  <div className="job-telemetry-live" aria-hidden="true">
                    <span className="telemetry-pulse-dot" />
                    <span className="telemetry-live-text">Luồng telemetry trực tiếp</span>
                    <span className="telemetry-live-attempt">Lần thử {job.data.attempt + 1}</span>
                  </div>
                ) : null}
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
                    <div className="step-marker-wrapper">
                      <div className="step-marker" aria-hidden="true">
                        {isDone ? <Check size={14} strokeWidth={2.5} /> : <span>{idx + 1}</span>}
                      </div>
                      {isCurrent ? <span className="node-active-ring" aria-hidden="true" /> : null}
                      {idx < LIFECYCLE_STEPS.length - 1 ? (
                        <div
                          className={`step-connector ${idx < currentStep || isCompleted ? "is-passed" : ""} ${idx === currentStep && isProcessing ? "is-flowing" : ""}`.trim()}
                          aria-hidden="true"
                        >
                          <span className="pipeline-flow-beam" />
                        </div>
                      ) : null}
                    </div>
                    <div className="step-meta">
                      <span className="step-label">{step.label}</span>
                      <span className="step-hint">{step.hint}</span>
                    </div>
                  </div>
                );
              })}
            </div>
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
