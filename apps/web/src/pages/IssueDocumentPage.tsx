import { FormEvent, useEffect, useRef, useState } from "react";
import { useMutation } from "@tanstack/react-query";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { FileUp, KeyRound, Sparkles } from "lucide-react";
import { useNavigate } from "react-router-dom";

import { CryptographicMotif, CryptographicMotifStage } from "../components/CryptographicMotif";
import { DocumentFileInput } from "../components/DocumentFileInput";
import { WorkflowSteps } from "../components/WorkflowSteps";
import { canCreateIssuance, useSession } from "../features/auth/session";
import { createIssuance } from "../features/issuances/issuances";
import { SafeApiError } from "../features/shared/apiError";
import { UploadStage, uploadIssuancePdf, validatePdf } from "../features/uploads/uploadIssuance";

gsap.registerPlugin(useGSAP);

const UUID_PATTERN = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

export type IssuancePipelineStage = "intake" | "hashing" | "decomposing" | "signing" | "sealed";

interface StageInfo {
  title: string;
  badge: string;
  desc: string;
}

const STAGE_TELEMETRY: Record<IssuancePipelineStage, StageInfo> = {
  intake: {
    title: "Tiếp nhận tài liệu",
    badge: "Tiếp nhận",
    desc: "Chuẩn bị nạp tài liệu vào khoang ký mật mã.",
  },
  hashing: {
    title: "Tính toán mã băm SHA-256",
    badge: "Băm phân đoạn",
    desc: "Trích xuất chuỗi băm chuẩn tắc từ nội dung nhị phân PDF.",
  },
  decomposing: {
    title: "Phân rã miền tần số DWT / DCT",
    badge: "Phân rã tín hiệu",
    desc: "Tách dải tần wavelet LL/LH/HL/HH để nhúng định danh vô hình.",
  },
  signing: {
    title: "Hội tụ nút ký số Ed25519",
    badge: "Ký chứng thực",
    desc: "Hội tụ các nút chữ ký số trên bản kê khai bảo toàn chứng cứ.",
  },
  sealed: {
    title: "Niêm phong chứng thư",
    badge: "Đã niêm phong",
    desc: "Bản cấp phát đã niêm phong, chuyển giao bộ giám sát tiến trình.",
  },
};

const PIPELINE_STEPS = [
  { id: "intake", label: "Tiếp nhận tệp", code: "01" },
  { id: "hashing", label: "Mã băm SHA-256", code: "02" },
  { id: "decomposing", label: "Phân rã DWT", code: "03" },
  { id: "signing", label: "Ký số Ed25519", code: "04" },
  { id: "sealed", label: "Niêm phong", code: "05" },
] as const;

const STAGE_ORDER: Record<IssuancePipelineStage, number> = {
  intake: 1,
  hashing: 2,
  decomposing: 3,
  signing: 4,
  sealed: 5,
};

export function IssueDocumentPage() {
  const session = useSession();
  const navigate = useNavigate();
  const abortRef = useRef<AbortController | null>(null);
  const chamberRef = useRef<HTMLDivElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [recipientId, setRecipientId] = useState("");
  const [stage, setStage] = useState<UploadStage | null>(null);
  const [validationError, setValidationError] = useState<string | null>(null);

  useEffect(() => () => abortRef.current?.abort(), []);

  const issuance = useMutation({
    mutationFn: async () => {
      if (!file) throw new SafeApiError("Chưa có tệp PDF. Chọn một tệp rồi thử lại.");
      validatePdf(file);
      if (!UUID_PATTERN.test(recipientId)) {
        throw new SafeApiError("Mã người nhận chưa đúng. Kiểm tra mã rồi thử lại.");
      }
      abortRef.current?.abort();
      const controller = new AbortController();
      abortRef.current = controller;
      const upload = await uploadIssuancePdf(file, setStage, controller.signal);
      setStage(null);
      return createIssuance(upload.uploadId, recipientId, controller.signal);
    },
    onSuccess: (created) => navigate(`/jobs/${created.job_id}`, {
      state: { issuanceId: created.id },
    }),
    onSettled: () => setStage(null),
  });

  const pipelineStage: IssuancePipelineStage = (() => {
    if (issuance.isSuccess) return "sealed";
    if (issuance.isPending) {
      if (stage === "hashing") return "hashing";
      if (stage === "intent" || stage === "uploading") return "decomposing";
      if (stage === "finalizing" || stage === null) return "signing";
    }
    return "intake";
  })();

  const motifStage: CryptographicMotifStage = (() => {
    if (issuance.isSuccess) return "sealed";
    if (issuance.isPending) {
      if (stage === "hashing") return "hashing";
      if (stage === "intent" || stage === "uploading") return "decomposing";
      if (stage === "finalizing" || stage === null) return "signing";
    }
    return "idle";
  })();

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function") {
        return;
      }

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(
          ".chamber-document-ghost, .chamber-decomp-band, .chamber-vector-ray, .chamber-convergence-ring, .chamber-beam, .chamber-seal-burst",
          { clearProps: "all" }
        );
        return;
      }

      if (pipelineStage === "intake") {
        if (file) {
          gsap.fromTo(
            ".chamber-document-ghost",
            { y: 12, opacity: 0.4, scale: 0.96 },
            { y: 0, opacity: 1, scale: 1, duration: 0.5, ease: "power2.out" }
          );
        } else {
          gsap.set(".chamber-document-ghost", { clearProps: "all" });
        }
        return;
      }

      if (pipelineStage === "hashing") {
        const tl = gsap.timeline({ repeat: -1 });
        tl.fromTo(
          ".chamber-beam",
          { y: -50, opacity: 0 },
          { y: 50, opacity: 0.85, duration: 1.2, ease: "power1.inOut" }
        ).to(".chamber-beam", { opacity: 0, duration: 0.2 });

        gsap.to(".chamber-document-ghost", {
          filter: "brightness(1.1)",
          repeat: -1,
          yoyo: true,
          duration: 0.5,
          ease: "sine.inOut",
        });
        return;
      }

      if (pipelineStage === "decomposing") {
        gsap.to(".chamber-document-ghost", {
          scale: 1.04,
          opacity: 0.5,
          duration: 0.4,
          ease: "power2.out",
        });
        const tl = gsap.timeline({ repeat: -1, yoyo: true });
        tl.to(".chamber-decomp-ll", { x: -8, y: -8, opacity: 1, duration: 0.9, ease: "sine.inOut" })
          .to(".chamber-decomp-hl", { x: 8, y: -8, opacity: 1, duration: 0.9, ease: "sine.inOut" }, "<")
          .to(".chamber-decomp-lh", { x: -8, y: 8, opacity: 1, duration: 0.9, ease: "sine.inOut" }, "<")
          .to(".chamber-decomp-hh", { x: 8, y: 8, opacity: 1, duration: 0.9, ease: "sine.inOut" }, "<");
        return;
      }

      if (pipelineStage === "signing") {
        const tl = gsap.timeline({ repeat: -1 });
        tl.fromTo(
          ".chamber-vector-ray",
          { strokeDashoffset: 40, opacity: 0.2 },
          { strokeDashoffset: 0, opacity: 1, stagger: 0.1, duration: 0.7, ease: "power2.inOut" }
        ).to(".chamber-vector-ray", { opacity: 0.25, duration: 0.35 });

        gsap.to(".chamber-convergence-ring", {
          scale: 0.88,
          repeat: -1,
          yoyo: true,
          duration: 0.85,
          ease: "sine.inOut",
        });
        return;
      }

      if (pipelineStage === "sealed") {
        const tl = gsap.timeline();
        tl.fromTo(
          ".chamber-seal-burst",
          { scale: 0.6, opacity: 0 },
          { scale: 1.3, opacity: 0.9, duration: 0.45, ease: "back.out(1.7)" }
        ).to(".chamber-seal-burst", { opacity: 0, scale: 1.6, duration: 0.3 });
        return;
      }
    },
    { scope: chamberRef, dependencies: [pipelineStage, Boolean(file)], revertOnUpdate: true }
  );

  const role = session.data?.user?.role;
  if (!canCreateIssuance(role)) {
    return (
      <main className="workspace-page">
        <header className="page-heading">
          <h1>Quyền chỉ đọc</h1>
          <p>Vai trò {role ?? "hiện tại"} có thể xem hồ sơ được cấp quyền nhưng không thể tạo bản cấp phát.</p>
        </header>
      </main>
    );
  }

  function selectFile(selected: File | undefined) {
    setValidationError(null);
    issuance.reset();
    if (!selected) {
      setFile(null);
      return;
    }
    try {
      validatePdf(selected);
      setFile(selected);
    } catch (error) {
      setFile(selected);
      setValidationError(error instanceof Error ? error.message : "Tệp chưa hợp lệ.");
    }
  }

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    issuance.mutate();
  }

  const error = validationError ?? issuance.error?.message ?? null;
  const telemetry = STAGE_TELEMETRY[pipelineStage];
  const displayTitle = file && pipelineStage === "intake" ? "Đã nạp tài liệu" : telemetry.title;
  const displayBadge = file && pipelineStage === "intake" ? "Đã tiếp nhận" : telemetry.badge;
  const displayDesc = file && pipelineStage === "intake"
    ? `Tệp ${file.name} đã nạp vào khoang, sẵn sàng tạo bản cấp phát.`
    : telemetry.desc;

  return (
    <main className="workspace-page">
      <header className="page-heading">
        <div className="page-heading-badge">
          <Sparkles size={14} aria-hidden="true" />
          <span>Cấp phát chứng thư số</span>
        </div>
        <h1>Tạo bản cấp phát</h1>
        <p>Chọn PDF và người nhận để tạo bản cấp phát riêng.</p>
      </header>

      <div className="workbench-layout">
        <section className="workbench" aria-labelledby="issuance-form-heading">
          <div className="workbench-caption">
            <h2 id="issuance-form-heading">Tệp và người nhận</h2>
            <p>Chọn tài liệu, sau đó nhập mã người nhận được cấp.</p>
          </div>

          <form className="form-stack issuance-form" onSubmit={submit} aria-busy={issuance.isPending}>
            <div className="field upload-dropzone" data-state={validationError ? "error" : file ? "success" : "default"}>
              {stage ? (
                <div className="vault-progress-glow" aria-hidden="true" />
              ) : null}
              <DocumentFileInput
                id="pdf-file"
                label="Tệp PDF"
                accept="application/pdf,.pdf"
                disabled={issuance.isPending}
                invalid={Boolean(validationError)}
                describedBy="pdf-help"
                filename={file?.name ?? null}
                onChange={selectFile}
              />
              <p className={validationError ? "field-help field-help-error" : "field-help"} id="pdf-help">
                {validationError ?? (file ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "PDF · tối đa 10 MiB · tối đa 50 trang")}
              </p>
            </div>

            <div className="field">
              <label htmlFor="recipient-id">Mã người nhận</label>
              <div className="input-with-icon">
                <span className="input-icon" aria-hidden="true"><KeyRound size={17} /></span>
                <input
                  id="recipient-id"
                  name="recipient-id"
                  inputMode="text"
                  autoComplete="off"
                  required
                  disabled={issuance.isPending}
                  aria-invalid={recipientId !== "" && !UUID_PATTERN.test(recipientId)}
                  aria-describedby="recipient-help"
                  placeholder="00000000-0000-0000-0000-000000000000"
                  value={recipientId}
                  onChange={(event) => setRecipientId(event.target.value.trim())}
                />
              </div>
              <p className="field-help" id="recipient-help">Nhập mã người nhận do hệ thống cấp.</p>
            </div>

            <WorkflowSteps stage={stage} />

            {error ? <p className="form-error" role="alert">{error}</p> : null}
            <button
              className="button button-primary"
              type="submit"
              disabled={issuance.isPending}
              data-state={issuance.isPending ? "loading" : error ? "error" : "default"}
            >
              <FileUp size={18} aria-hidden="true" />
              <span>{issuance.isPending ? "Đang tạo bản cấp phát" : "Tạo bản cấp phát"}</span>
            </button>
          </form>
        </section>

        <aside className="workbench-aside" aria-label="Thông tin quy trình">
          <section className="aside-card issuance-chamber" ref={chamberRef} aria-label="Khoang ký số mật mã" data-stage={pipelineStage}>
            <div className="chamber-header">
              <div className="chamber-header-meta">
                <span className="chamber-badge">Khoang ký mật mã</span>
                <h3 className="chamber-title">{displayTitle}</h3>
              </div>
              <span className="chamber-stage-pill" data-stage={pipelineStage}>
                {displayBadge}
              </span>
            </div>

            <div className="chamber-viewport">
              <div className="chamber-grid-backdrop" aria-hidden="true" />

              <div className="chamber-document-ghost" aria-hidden="true" data-has-file={Boolean(file)}>
                <div className="chamber-doc-card">
                  <div className="chamber-doc-header">
                    <span className="chamber-doc-tag">PDF</span>
                    <span className="chamber-doc-status">{file ? `${Math.max(1, Math.ceil(file.size / 1024))} KiB` : "Chờ tệp"}</span>
                  </div>
                  <div className="chamber-doc-lines">
                    <div className="chamber-doc-line" />
                    <div className="chamber-doc-line chamber-doc-line-short" />
                    <div className="chamber-doc-line" />
                  </div>
                </div>
              </div>

              <div className="chamber-decomp-layers" aria-hidden="true">
                <div className="chamber-decomp-band chamber-decomp-ll">
                  <span>LL</span>
                  <small>Xấp xỉ</small>
                </div>
                <div className="chamber-decomp-band chamber-decomp-hl">
                  <span>HL</span>
                  <small>Ngang</small>
                </div>
                <div className="chamber-decomp-band chamber-decomp-lh">
                  <span>LH</span>
                  <small>Dọc</small>
                </div>
                <div className="chamber-decomp-band chamber-decomp-hh">
                  <span>HH</span>
                  <small>Chéo</small>
                </div>
              </div>

              <svg className="chamber-convergence-svg" viewBox="0 0 200 200" aria-hidden="true">
                <line x1="20" y1="20" x2="85" y2="85" className="chamber-vector-ray" />
                <line x1="180" y1="20" x2="115" y2="85" className="chamber-vector-ray" />
                <line x1="180" y1="180" x2="115" y2="115" className="chamber-vector-ray" />
                <line x1="20" y1="180" x2="85" y2="115" className="chamber-vector-ray" />
                <circle cx="100" cy="100" r="42" className="chamber-convergence-ring" />
              </svg>

              <div className="chamber-beam" aria-hidden="true" />
              <div className="chamber-seal-burst" aria-hidden="true" />

              <CryptographicMotif stage={motifStage} size={160} className="chamber-motif" />
            </div>

            <div className="chamber-pipeline-track" aria-label="Các bước xử lý mật mã">
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
                <span className="chamber-telemetry-value" title={file?.name ?? "Chờ tệp PDF"}>
                  {file ? file.name : "Chờ tệp PDF"}
                </span>
              </div>
              <div className="chamber-telemetry-row">
                <span className="chamber-telemetry-key">Mã người nhận</span>
                <span className="chamber-telemetry-value" title={recipientId || "Chưa nhập"}>
                  {recipientId ? (recipientId.length > 16 ? `${recipientId.slice(0, 8)}…${recipientId.slice(-4)}` : recipientId) : "Chưa nhập"}
                </span>
              </div>
              <div className="chamber-telemetry-row">
                <span className="chamber-telemetry-key">Trạng thái khoang</span>
                <span className="chamber-telemetry-value chamber-telemetry-desc">{displayDesc}</span>
              </div>
            </div>
          </section>

          <div className="aside-card">
            <h3>Quy trình cấp phát</h3>
            <ol className="aside-steps">
              <li>
                <strong>Kiểm tra tệp</strong>
                <span>Tính toán mã băm SHA-256 bảo vệ nội dung.</span>
              </li>
              <li>
                <strong>Nhúng dấu vết</strong>
                <span>Chèn định danh bảo mật bằng thuật toán chuyên dụng.</span>
              </li>
              <li>
                <strong>Ký số chứng nhận</strong>
                <span>Tạo chữ ký số Ed25519 cho bản kê khai toàn vẹn.</span>
              </li>
            </ol>
          </div>
          <div className="aside-card aside-tip">
            <h4>Lưu ý an toàn</h4>
            <p>Mỗi tài liệu cấp phát được tạo riêng biệt. Hãy lưu trữ bản PDF kết quả cẩn thận.</p>
          </div>
        </aside>
      </div>
    </main>
  );
}
