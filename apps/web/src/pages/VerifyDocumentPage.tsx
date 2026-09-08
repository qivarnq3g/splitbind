import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { FileCheck, Search, ShieldCheck } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { CryptographicMotif, CryptographicMotifStage } from "../components/CryptographicMotif";
import { DocumentFileInput } from "../components/DocumentFileInput";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { canCreateVerification, useSession } from "../features/auth/session";
import { SafeApiError } from "../features/shared/apiError";
import { type UploadStage, uploadVerificationPdf, validateVerificationFile } from "../features/uploads/uploadIssuance";
import { createVerification } from "../features/verifications/verifications";

gsap.registerPlugin(useGSAP);

export type VerificationPipelineStage =
  | "intake"
  | "optical_scan"
  | "signal_extraction"
  | "signal_comparison"
  | "resolution_handoff";

interface StageInfo {
  title: string;
  badge: string;
  desc: string;
}

const STAGE_TELEMETRY: Record<VerificationPipelineStage, StageInfo> = {
  intake: {
    title: "Tiếp nhận tài liệu kiểm tra",
    badge: "Tiếp nhận",
    desc: "Tài liệu nạp vào buồng kiểm định, sẵn sàng quét đa tầng.",
  },
  optical_scan: {
    title: "Quét ma trận quang học",
    badge: "Quét quang học",
    desc: "Tia quét laser đa tầng khảo sát ma trận điểm ảnh và mã băm toàn vẹn.",
  },
  signal_extraction: {
    title: "Tách dải tần DWT quan sát",
    badge: "Tách dải tần",
    desc: "Trích xuất lớp tín hiệu tần số wavelet (LL/LH/HL/HH) từ tài liệu.",
  },
  signal_comparison: {
    title: "Đối sánh tín hiệu & sai biệt",
    badge: "Đối sánh tín hiệu",
    desc: "So sánh dải tần quan sát với tín hiệu kỳ vọng để phát hiện can thiệp.",
  },
  resolution_handoff: {
    title: "Chuyển tiếp lập hồ sơ kiểm định",
    badge: "Chuyển tiếp",
    desc: "Hoàn tất thu thập bằng chứng, chuyển tiếp tiến trình lập hồ sơ giám định.",
  },
};

const PIPELINE_STEPS = [
  { id: "intake", label: "Tiếp nhận tệp", code: "01" },
  { id: "optical_scan", label: "Quét quang học", code: "02" },
  { id: "signal_extraction", label: "Tách dải tần", code: "03" },
  { id: "signal_comparison", label: "Đối sánh tín hiệu", code: "04" },
  { id: "resolution_handoff", label: "Chuyển tiếp", code: "05" },
] as const;

const STAGE_ORDER: Record<VerificationPipelineStage, number> = {
  intake: 1,
  optical_scan: 2,
  signal_extraction: 3,
  signal_comparison: 4,
  resolution_handoff: 5,
};

export function VerifyDocumentPage() {
  const session = useSession();
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);
  const chamberRef = useRef<HTMLDivElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [stage, setStage] = useState<UploadStage | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const verification = useMutation({
    mutationFn: async () => {
      if (!file) throw new SafeApiError("Chưa có tệp. Chọn một tệp rồi thử lại.");
      validateVerificationFile(file);
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const upload = await uploadVerificationPdf(file, setStage, controller.signal);
      setStage(null);
      return createVerification(upload.uploadId, controller.signal);
    },
    onSuccess: (created) => navigate(`/jobs/${created.job_id}`, {
      state: { verificationId: created.id },
    }),
    onSettled: () => setStage(null),
  });

  const pipelineStage: VerificationPipelineStage = (() => {
    if (verification.isSuccess) return "resolution_handoff";
    if (verification.isPending) {
      if (stage === "hashing") return "optical_scan";
      if (stage === "intent" || stage === "uploading") return "signal_extraction";
      if (stage === "finalizing") return "signal_comparison";
      return "resolution_handoff";
    }
    return "intake";
  })();

  const motifStage: CryptographicMotifStage = verification.isPending || stage !== null ? "verifying" : "idle";

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return;
      }

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(
          ".chamber-document-ghost, .verification-laser-primary, .verification-laser-secondary, .verification-frequency-grid, .verification-comparison-tracks, .verification-region-reticle, .verification-resolution-wave",
          { clearProps: "all" }
        );
        return;
      }

      if (pipelineStage === "intake") {
        if (file) {
          gsap.fromTo(
            ".chamber-document-ghost",
            { y: 14, opacity: 0.35, scale: 0.95 },
            { y: 0, opacity: 1, scale: 1, duration: 0.45, ease: "power2.out" }
          );
          gsap.fromTo(
            ".chamber-corner-bracket",
            { opacity: 0.25, scale: 0.9 },
            { opacity: 0.85, scale: 1, duration: 0.5, stagger: 0.05, ease: "power2.out" }
          );
        } else {
          gsap.set(".chamber-document-ghost, .chamber-corner-bracket", { clearProps: "all" });
        }
        return;
      }

      if (pipelineStage === "optical_scan") {
        const tl = gsap.timeline({ repeat: -1 });
        tl.fromTo(
          ".verification-laser-primary",
          { y: -65, opacity: 0 },
          { y: 65, opacity: 0.9, duration: 1.1, ease: "power1.inOut" }
        ).to(".verification-laser-primary", { opacity: 0, duration: 0.15 });

        const tlSec = gsap.timeline({ repeat: -1, delay: 0.18 });
        tlSec.fromTo(
          ".verification-laser-secondary",
          { y: -65, opacity: 0 },
          { y: 65, opacity: 0.65, duration: 1.1, ease: "power1.inOut" }
        ).to(".verification-laser-secondary", { opacity: 0, duration: 0.15 });

        gsap.to(".chamber-document-ghost", {
          filter: "brightness(1.16) contrast(1.06)",
          repeat: -1,
          yoyo: true,
          duration: 0.5,
          ease: "sine.inOut",
        });
        return;
      }

      if (pipelineStage === "signal_extraction") {
        gsap.to(".chamber-document-ghost", {
          scale: 1.03,
          opacity: 0.55,
          duration: 0.35,
          ease: "power2.out",
        });

        gsap.fromTo(
          ".verification-freq-cell",
          { opacity: 0.25, scale: 0.94 },
          { opacity: 0.95, scale: 1, stagger: 0.12, duration: 0.75, repeat: -1, yoyo: true, ease: "sine.inOut" }
        );

        gsap.to(".verification-laser-primary", {
          y: 0,
          opacity: 0.8,
          scaleX: 1.15,
          repeat: -1,
          yoyo: true,
          duration: 0.4,
          ease: "power1.inOut",
        });
        return;
      }

      if (pipelineStage === "signal_comparison") {
        gsap.to(".signal-bar-observed", {
          scaleY: 0.9,
          transformOrigin: "bottom",
          duration: 0.35,
          repeat: -1,
          yoyo: true,
          stagger: 0.06,
          ease: "power1.inOut",
        });

        gsap.to(".signal-bar-expected", {
          scaleY: 0.85,
          transformOrigin: "bottom",
          duration: 0.45,
          repeat: -1,
          yoyo: true,
          stagger: 0.06,
          ease: "power1.inOut",
        });

        gsap.fromTo(
          ".verification-region-reticle",
          { scale: 0.82, opacity: 0.2 },
          { scale: 1.12, opacity: 0.95, duration: 0.7, repeat: -1, yoyo: true, stagger: 0.15, ease: "sine.inOut" }
        );
        return;
      }

      if (pipelineStage === "resolution_handoff") {
        const tl = gsap.timeline();
        tl.fromTo(
          ".verification-resolution-wave",
          { scale: 0.65, opacity: 0 },
          { scale: 1.35, opacity: 0.9, duration: 0.45, ease: "power2.out" }
        ).to(".verification-resolution-wave", { opacity: 0, scale: 1.7, duration: 0.3 });
        return;
      }
    },
    { scope: chamberRef, dependencies: [pipelineStage, Boolean(file)], revertOnUpdate: true }
  );

  const role = session.data?.user?.role;
  if (!canCreateVerification(role)) {
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Không có quyền tạo kiểm chứng</h1>
          <p>Chỉ vai trò administrator hoặc verifier được tải tài liệu và bắt đầu một công việc kiểm chứng mới.</p>
        </header>
      </main>
    );
  }

  function selectFile(selected: File | undefined) {
    setValidationError(null);
    verification.reset();
    if (!selected) {
      setFile(null);
      return;
    }
    try {
      validateVerificationFile(selected);
      setFile(selected);
    } catch (error) {
      setFile(selected);
      setValidationError(error instanceof Error ? error.message : "Tệp chưa hợp lệ.");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    verification.mutate();
  }

  const error = validationError ?? verification.error?.message ?? null;
  const telemetry = STAGE_TELEMETRY[pipelineStage];
  const displayTitle = file && pipelineStage === "intake" ? "Đã nạp tài liệu" : telemetry.title;
  const displayBadge = file && pipelineStage === "intake" ? "Đã tiếp nhận" : telemetry.badge;
  const displayDesc = file && pipelineStage === "intake"
    ? `Tệp ${file.name} đã nạp vào buồng kiểm tra, sẵn sàng tiến hành quét đa tầng.`
    : telemetry.desc;

  const fileTypeTag = file
    ? file.name.toLowerCase().endsWith(".pdf")
      ? "PDF"
      : "IMG"
    : "DOC";

  const fileFormatLabel = file
    ? file.name.toLowerCase().endsWith(".pdf")
      ? "PDF Document"
      : file.type || "Ảnh raster"
    : "Chưa chọn";

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <div className="page-heading-badge">
          <ShieldCheck size={14} aria-hidden="true" />
          <span>Kiểm tra tính toàn vẹn</span>
        </div>
        <h1>Xác minh tài liệu</h1>
        <p>Tải tài liệu lên để xem kết quả kiểm tra kỹ thuật.</p>
      </header>

      <div className="workbench-layout">
        <section className="workbench" aria-labelledby="verification-form-heading">
          <div className="workbench-caption">
            <h2 id="verification-form-heading">Tệp cần kiểm tra</h2>
            <p>Hỗ trợ PDF, PNG và JPEG.</p>
          </div>

          <form className="form-stack" onSubmit={submit} aria-busy={verification.isPending}>
            <div className="field upload-dropzone" data-state={validationError ? "error" : file ? "success" : "default"}>
              {stage ? (
                <div className="scan-laser-wrap" aria-hidden="true">
                  <div className="scan-laser-beam scan-laser-beam-primary" />
                  <div className="scan-laser-beam scan-laser-beam-secondary" />
                </div>
              ) : null}
              <DocumentFileInput
                id="verification-pdf"
                label="Tệp cần kiểm chứng"
                accept="application/pdf,image/png,image/jpeg,.pdf,.png,.jpg,.jpeg"
                disabled={verification.isPending}
                invalid={Boolean(validationError)}
                describedBy="verification-pdf-help"
                filename={file?.name ?? null}
                onChange={selectFile}
              />
              <p className={validationError ? "field-help field-help-error" : "field-help"} id="verification-pdf-help">
                {validationError ?? (file ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "Tối đa 10 MiB · PDF tối đa 50 trang")}
              </p>
            </div>

            <WorkflowSteps stage={stage} />

            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button
              className="button button-primary"
              type="submit"
              disabled={verification.isPending}
              data-state={verification.isPending ? "loading" : error ? "error" : "default"}
            >
              <Search size={18} aria-hidden="true" />
              <span>{verification.isPending ? "Đang bắt đầu xác minh" : "Bắt đầu xác minh"}</span>
            </button>
          </form>
        </section>

        <aside className="workbench-aside" aria-label="Thông tin xác minh">
          <section
            className="aside-card verification-chamber"
            ref={chamberRef}
            aria-label="Buồng kiểm định mật mã"
            data-stage={pipelineStage}
          >
            <div className="chamber-header">
              <div className="chamber-header-meta">
                <span className="chamber-badge">Buồng kiểm định mật mã</span>
                <h3 className="chamber-title">{displayTitle}</h3>
              </div>
              <span className="chamber-stage-pill" data-stage={pipelineStage}>
                {displayBadge}
              </span>
            </div>

            <div className="chamber-viewport verification-viewport">
              <div className="chamber-grid-backdrop verification-grid-backdrop" aria-hidden="true" />

              <div className="chamber-corner-bracket corner-top-left" aria-hidden="true" />
              <div className="chamber-corner-bracket corner-top-right" aria-hidden="true" />
              <div className="chamber-corner-bracket corner-bottom-left" aria-hidden="true" />
              <div className="chamber-corner-bracket corner-bottom-right" aria-hidden="true" />

              <div className="chamber-document-ghost verification-doc-ghost" aria-hidden="true" data-has-file={Boolean(file)}>
                <div className="chamber-doc-card verification-doc-card">
                  <div className="chamber-doc-header">
                    <span className="chamber-doc-tag">{fileTypeTag}</span>
                    <span className="chamber-doc-status">{file ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "Chờ tệp"}</span>
                  </div>
                  <div className="chamber-doc-lines">
                    <div className="chamber-doc-line" />
                    <div className="chamber-doc-line chamber-doc-line-short" />
                    <div className="chamber-doc-line" />
                  </div>
                </div>
              </div>

              <div className="verification-laser-primary" aria-hidden="true" />
              <div className="verification-laser-secondary" aria-hidden="true" />

              <div className="verification-frequency-grid" aria-hidden="true">
                <div className="verification-freq-cell freq-ll">
                  <span>LL</span>
                  <small>Xấp xỉ</small>
                </div>
                <div className="verification-freq-cell freq-hl">
                  <span>HL</span>
                  <small>Ngang</small>
                </div>
                <div className="verification-freq-cell freq-lh">
                  <span>LH</span>
                  <small>Dọc</small>
                </div>
                <div className="verification-freq-cell freq-hh">
                  <span>HH</span>
                  <small>Chéo</small>
                </div>
              </div>

              <div className="verification-comparison-tracks" aria-hidden="true">
                <div className="signal-track-group">
                  <span className="signal-track-label">Kỳ vọng</span>
                  <div className="signal-bars-row">
                    <div className="verification-signal-bar signal-bar-expected" style={{ height: "14px" }} />
                    <div className="verification-signal-bar signal-bar-expected" style={{ height: "20px" }} />
                    <div className="verification-signal-bar signal-bar-expected" style={{ height: "16px" }} />
                    <div className="verification-signal-bar signal-bar-expected" style={{ height: "22px" }} />
                    <div className="verification-signal-bar signal-bar-expected" style={{ height: "18px" }} />
                  </div>
                </div>
                <div className="signal-track-group">
                  <span className="signal-track-label">Quan sát</span>
                  <div className="signal-bars-row">
                    <div className="verification-signal-bar signal-bar-observed" style={{ height: "16px" }} />
                    <div className="verification-signal-bar signal-bar-observed" style={{ height: "18px" }} />
                    <div className="verification-signal-bar signal-bar-observed" style={{ height: "15px" }} />
                    <div className="verification-signal-bar signal-bar-observed" style={{ height: "21px" }} />
                    <div className="verification-signal-bar signal-bar-observed" style={{ height: "19px" }} />
                  </div>
                </div>
              </div>

              <div className="verification-region-reticle reticle-a" aria-hidden="true">
                <div className="region-reticle-inner" />
              </div>
              <div className="verification-region-reticle reticle-b" aria-hidden="true">
                <div className="region-reticle-inner" />
              </div>

              <div className="verification-resolution-wave" aria-hidden="true" />

              <CryptographicMotif stage={motifStage} size={160} className="chamber-motif" />
            </div>

            <div className="chamber-pipeline-track" aria-label="Các bước quét kiểm định">
              {PIPELINE_STEPS.map((step) => {
                const isCurrent = pipelineStage === step.id;
                const isPast = STAGE_ORDER[pipelineStage] > STAGE_ORDER[step.id];
                const stepState = isCurrent ? (step.id === "intake" && !file ? "pending" : "active") : isPast ? "completed" : "pending";
                return (
                  <div key={step.id} className="chamber-pipeline-node" data-state={stepState}>
                    <span className="chamber-node-index">{step.code}</span>
                    <span className="chamber-node-label">{step.label}</span>
                  </div>
                );
              })}
            </div>

            <div className="chamber-telemetry">
              <div className="chamber-telemetry-row">
                <span className="chamber-telemetry-key">Tài liệu</span>
                <span className="chamber-telemetry-value" title={file?.name ?? "Chờ tệp kiểm tra"}>
                  {file ? file.name : "Chờ tệp kiểm tra"}
                </span>
              </div>
              <div className="chamber-telemetry-row">
                <span className="chamber-telemetry-key">Định dạng</span>
                <span className="chamber-telemetry-value" title={fileFormatLabel}>
                  {fileFormatLabel}
                </span>
              </div>
              <div className="chamber-telemetry-row">
                <span className="chamber-telemetry-key">Phương thức</span>
                <span className="chamber-telemetry-value" title="Quét đa tầng quang học & dải tần DWT">
                  Quét đa tầng quang học & dải tần DWT
                </span>
              </div>
              <div className="chamber-telemetry-row">
                <span className="chamber-telemetry-key">Trạng thái buồng</span>
                <span className="chamber-telemetry-value chamber-telemetry-desc">{displayDesc}</span>
              </div>
            </div>
          </section>

          <div className="aside-card">
            <h3>Phương thức xác minh</h3>
            <ul className="aside-features">
              <li>
                <strong>Đối chiếu mã băm</strong>
                <span>Xác nhận tệp có khớp chính xác 100% với bản phát hành hay không.</span>
              </li>
              <li>
                <strong>Kiểm tra chữ ký số</strong>
                <span>Xác thực tính hợp lệ của chữ ký Ed25519 từ máy chủ cấp phát.</span>
              </li>
              <li>
                <strong>Phát hiện chỉnh sửa</strong>
                <span>Dò quét các vùng bị can thiệp trên tài liệu.</span>
              </li>
            </ul>
          </div>
          <div className="aside-card aside-tip">
            <h4>Báo cáo kỹ thuật</h4>
            <p>Kết quả thể hiện dưới dạng bằng chứng toán học khách quan, đảm bảo tính pháp lý độc lập.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
