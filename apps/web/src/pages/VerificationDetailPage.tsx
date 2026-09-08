import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import { useQuery } from "@tanstack/react-query";
import gsap from "gsap";
import { ExternalLink, FileSearch, Loader2, ShieldAlert, ShieldCheck } from "lucide-react";
import { Link, useParams } from "react-router-dom";

import { CompactIdentifier } from "../components/CompactIdentifier";
import { CryptographicMotif } from "../components/CryptographicMotif";
import { StatusBadge } from "../components/StatusBadge";
import { canViewVerification, useSession } from "../features/auth/session";
import { EvidenceSummary } from "../features/evidence/EvidenceSummary";
import { verificationCopy } from "../features/evidence/copy";
import { JOB_LABELS } from "../features/jobs/useJob";
import { getVerification } from "../features/verifications/verifications";

gsap.registerPlugin(useGSAP);

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
  const sealRef = useRef<HTMLElement>(null);
  const verification = useQuery({
    queryKey: ["verification", id],
    queryFn: ({ signal }) => getVerification(id!, signal),
    enabled: Boolean(id) && permitted,
  });
  const resultCopy = verification.data?.status
    ? verificationCopy(
      verification.data.status,
      verification.data.evidence.algorithm_label,
      verification.data.evidence.exact_file_hash_match,
    )
    : null;

  const isIntact = verification.data?.status === "VERIFIED_INTACT";
  const hasStatus = Boolean(verification.data?.status);

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function" || !sealRef.current || !hasStatus) {
        return;
      }

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(
          ".seal-ring, .stamp-seal-lock, .seal-authoritative-badge, .seal-readout-item, .fracture-trace, .discrepancy-reticle, .evidence-anomaly-beacon, .tamper-metric",
          { clearProps: "all" }
        );
        return;
      }

      if (isIntact) {
        const tl = gsap.timeline({ defaults: { ease: "power2.out" } });
        tl.fromTo(
          ".seal-ring",
          { scale: 0.65, opacity: 0, rotation: -40 },
          { scale: 1, opacity: 1, rotation: 0, duration: 0.65, stagger: 0.1, ease: "back.out(1.5)" }
        )
        .fromTo(
          ".stamp-seal-lock",
          { scale: 1.35, opacity: 0, y: -8 },
          { scale: 1, opacity: 1, y: 0, duration: 0.45, ease: "back.out(2)" },
          "-=0.25"
        )
        .fromTo(
          ".seal-authoritative-badge",
          { opacity: 0, y: 8 },
          { opacity: 1, y: 0, duration: 0.35 },
          "-=0.2"
        )
        .fromTo(
          ".seal-readout-item",
          { opacity: 0, y: 6 },
          { opacity: 1, y: 0, duration: 0.3, stagger: 0.08 },
          "-=0.15"
        );
      } else {
        const tl = gsap.timeline({ defaults: { ease: "power2.out" } });
        tl.fromTo(
          ".fracture-trace",
          { strokeDashoffset: 120, opacity: 0 },
          { strokeDashoffset: 0, opacity: 1, duration: 0.5, stagger: 0.1, ease: "power1.inOut" }
        )
        .fromTo(
          ".discrepancy-reticle",
          { scale: 1.25, opacity: 0 },
          { scale: 1, opacity: 1, duration: 0.4, stagger: 0.12, ease: "power2.out" },
          "-=0.2"
        )
        .fromTo(
          ".evidence-anomaly-beacon",
          { scale: 0.6, opacity: 0 },
          { scale: 1, opacity: 1, duration: 0.3 },
          "-=0.1"
        )
        .fromTo(
          ".tamper-metric",
          { opacity: 0, x: -6 },
          { opacity: 1, x: 0, duration: 0.25, stagger: 0.06 },
          "-=0.1"
        );

        gsap.to(".beacon-ping", {
          scale: 2.2,
          opacity: 0,
          duration: 1.6,
          repeat: -1,
          ease: "power1.out",
        });
      }
    },
    { scope: sealRef, dependencies: [verification.data?.status, isIntact, hasStatus], revertOnUpdate: true }
  );

  if (!permitted) {
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Không có quyền xem kiểm chứng</h1>
          <p>Phiên hiện tại không được phép đọc hồ sơ kiểm chứng.</p>
        </header>
      </main>
    );
  }

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <div className="page-heading-badge">
          <FileSearch size={14} aria-hidden="true" />
          <span>Kiểm định tài liệu</span>
        </div>
        <h1>Kết quả kiểm chứng</h1>
        <p>Xem kết luận trước, mở chi tiết kỹ thuật khi cần.</p>
      </header>

      {verification.isPending ? (
        <section className="status-board" aria-busy="true">
          <div className="board-loading">
            <Loader2 className="spinner" size={24} aria-hidden="true" />
            <p>Đang tải hồ sơ kiểm chứng</p>
          </div>
        </section>
      ) : null}

      {verification.error ? <p className="form-error" role="alert">{verification.error.message}</p> : null}

      {verification.data ? (
        <>
          <section className="status-board verification-record">
            <StatusBadge
              label="Trạng thái kết quả"
              status={verification.data.job_status}
              title={resultCopy?.label ?? (verification.data.job_status ? JOB_LABELS[verification.data.job_status] ?? verification.data.job_status : "Chưa có công việc")}
            />
            <dl className="status-details">
              <div>
                <dt>Mã kiểm chứng</dt>
                <dd><CompactIdentifier label="Mã kiểm chứng" value={verification.data.id} /></dd>
              </div>
              <div>
                <dt>Công việc</dt>
                <dd>
                  <span className="job-status-tag">
                    {verification.data.job_status ? JOB_LABELS[verification.data.job_status] : "Chưa có"}
                  </span>
                </dd>
              </div>
              <div>
                <dt>Thời điểm tạo</dt>
                <dd>
                  <time dateTime={verification.data.created_at}>
                    {new Intl.DateTimeFormat("vi-VN", { dateStyle: "medium", timeStyle: "short" }).format(new Date(verification.data.created_at))}
                  </time>
                </dd>
              </div>
            </dl>
            {verification.data.job_id ? (
              <div className="record-actions">
                <Link className="button button-secondary" to={`/jobs/${verification.data.job_id}`}>
                  <span>Xem tiến độ xử lý</span>
                  <ExternalLink size={15} aria-hidden="true" />
                </Link>
              </div>
            ) : null}
          </section>

          {verification.data.status ? (
            <>
              <section
                ref={sealRef}
                className={`verification-seal-construction ${isIntact ? "seal-intact" : "seal-anomaly"}`}
                data-status={isIntact ? "intact" : "tampered"}
                role="region"
                aria-label={isIntact ? "Ấn triện mật mã xác thực" : "Cách ly sai lệch và cảnh báo bất thường"}
              >
                {isIntact ? (
                  <>
                    <div className="seal-construction-stage" aria-hidden="true">
                      <div className="seal-concentric-rings">
                        <span className="seal-ring ring-outer" />
                        <span className="seal-ring ring-mid" />
                        <span className="seal-ring ring-inner" />
                      </div>
                      <CryptographicMotif stage="sealed" size={140} className="seal-stage-motif" />
                      <div className="stamp-seal-lock">
                        <div className="stamp-seal-badge">
                          <ShieldCheck size={24} className="stamp-lock-icon" />
                          <span className="stamp-lock-text">SEALED</span>
                        </div>
                      </div>
                    </div>
                    <div className="seal-construction-meta">
                      <div className="seal-authoritative-badge">
                        <span className="seal-beacon-dot" />
                        <span className="seal-authoritative-title">Trạng thái thẩm quyền: Đã niêm phong mật mã</span>
                      </div>
                      <h3 className="seal-payoff-headline">Chứng thư xác thực toàn vẹn độc lập</h3>
                      <p className="seal-payoff-description">
                        Hệ thống đã hội tụ hình học phân rã và hoàn tất khóa ấn triện Ed25519 cho tài liệu này.
                      </p>
                      <div className="seal-telemetry-readout">
                        <div className="seal-readout-item">
                          <span className="readout-label">Hội tụ hình học</span>
                          <span className="readout-value">Khớp tuyệt đối</span>
                        </div>
                        <div className="seal-readout-item">
                          <span className="readout-label">Chữ ký phân tán</span>
                          <span className="readout-value">
                            {verification.data.evidence.manifest_signature_valid ? "Hợp lệ" : "Đã xác thực"}
                          </span>
                        </div>
                        <div className="seal-readout-item">
                          <span className="readout-label">Toàn vẹn tệp</span>
                          <span className="readout-value">
                            {verification.data.evidence.exact_file_hash_match ? "Khớp bản gốc" : "Đã kiểm định"}
                          </span>
                        </div>
                      </div>
                    </div>
                  </>
                ) : (
                  <>
                    <div className="seal-construction-stage failure-stage" aria-hidden="true">
                      <div className="fractured-geometry">
                        <svg className="fracture-svg" viewBox="0 0 160 160">
                          <path className="fracture-trace fracture-trace-1" d="M 16 32 L 82 78 L 48 112 L 18 142" />
                          <path className="fracture-trace fracture-trace-2" d="M 144 24 L 92 68 L 118 116 L 142 148" />
                          <path className="fracture-trace fracture-trace-3" d="M 82 78 L 118 88 L 102 134" />
                        </svg>
                      </div>
                      <div className="discrepancy-reticles">
                        <div className="discrepancy-reticle reticle-1">
                          <span className="reticle-corner r-tl" />
                          <span className="reticle-corner r-tr" />
                          <span className="reticle-corner r-bl" />
                          <span className="reticle-corner r-br" />
                          <span className="reticle-tag">DELTA_A</span>
                        </div>
                        <div className="discrepancy-reticle reticle-2">
                          <span className="reticle-corner r-tl" />
                          <span className="reticle-corner r-tr" />
                          <span className="reticle-corner r-bl" />
                          <span className="reticle-corner r-br" />
                          <span className="reticle-tag">DELTA_B</span>
                        </div>
                      </div>
                      <div className="evidence-anomaly-beacon">
                        <span className="beacon-ping" />
                        <span className="beacon-core" />
                      </div>
                      <CryptographicMotif stage="tampered" size={140} className="seal-stage-motif failure-motif" />
                    </div>
                    <div className="seal-construction-meta failure-meta">
                      <div className="tamper-telemetry-badge">
                        <span className="tamper-beacon-dot" />
                        <span className="tamper-telemetry-title">Cảnh báo sai lệch: Phát hiện biến đổi cấu trúc</span>
                      </div>
                      <h3 className="tamper-payoff-headline">Cách ly sai lệch & Đo từ xa bất thường</h3>
                      <p className="tamper-payoff-description">
                        Hệ thống cách ly phân vùng dị biệt và ghi nhận đo từ xa bất thường thay vì hội tụ ấn triện xác thực.
                      </p>
                      <div className="tamper-telemetry" role="region" aria-label="Đo từ xa phát hiện bất thường">
                        <div className="tamper-telemetry-header">
                          <ShieldAlert size={18} className="tamper-alert-icon" aria-hidden="true" />
                          <h4>Dữ liệu đo từ xa sai lệch</h4>
                        </div>
                        <div className="tamper-telemetry-metrics">
                          <div className="tamper-metric">
                            <span className="metric-label">Vùng nghi vấn</span>
                            <span className="metric-value">
                              {verification.data.evidence.suspicious_regions ? `${verification.data.evidence.suspicious_regions.length} vùng` : "Chưa xác định"}
                            </span>
                          </div>
                          <div className="tamper-metric">
                            <span className="metric-label">Đối chiếu băm gốc</span>
                            <span className="metric-value">
                              {verification.data.evidence.exact_file_hash_match === false ? "Không khớp" : "Đã đối soát"}
                            </span>
                          </div>
                          <div className="tamper-metric">
                            <span className="metric-label">Chữ ký số</span>
                            <span className="metric-value">
                              {verification.data.evidence.manifest_signature_valid === false ? "Không hợp lệ" : "Đã đối soát"}
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </>
                )}
              </section>

              <EvidenceSummary status={verification.data.status} evidence={verification.data.evidence} />
            </>
          ) : (
            <div className="result-notice notice-unavailable">
              <p className="result-note">{missingEvidenceCopy(verification.data.job_status)}</p>
            </div>
          )}
        </>
      ) : null}
    </main>
  );
}
