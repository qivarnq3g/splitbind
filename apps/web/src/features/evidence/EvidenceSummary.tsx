import { useRef } from "react";
import { useGSAP } from "@gsap/react";
import gsap from "gsap";
import { ScrollTrigger } from "gsap/ScrollTrigger";

import type { components } from "../../api/generated/schema";
import { IntegrityMap } from "./IntegrityMap";
import { LIMITATION_COPY, STATUS_LIMITATIONS, isIntegrityNonExact, verificationCopy, type VerificationStatus } from "./copy";

gsap.registerPlugin(useGSAP);
if (typeof window !== "undefined" && typeof window.matchMedia === "function") {
  gsap.registerPlugin(ScrollTrigger);
}

type Evidence = components["schemas"]["VerificationEvidence"];

function signatureLabel(value: boolean | null | undefined): string {
  if (value === true) return "Hợp lệ";
  if (value === false) return "Không hợp lệ";
  return "API chưa cung cấp";
}

function hashLabel(value: boolean | null | undefined): string {
  if (value === true) return "Khớp";
  if (value === false) return "Không khớp";
  return "API chưa cung cấp";
}

function scoreLabel(value: number | null | undefined): string {
  return typeof value === "number"
    ? value.toLocaleString("vi-VN", { maximumFractionDigits: 4 })
    : "API chưa cung cấp";
}

export function EvidenceSummary({ status, evidence }: { status: VerificationStatus; evidence: Evidence }) {
  const rootRef = useRef<HTMLElement>(null);
  const knownLimitations = (evidence.limitations ?? []).filter((id) => id in LIMITATION_COPY);
  const integrityNonExact = isIntegrityNonExact(evidence.algorithm_label, evidence.exact_file_hash_match);
  const defaultLimitations = integrityNonExact
    ? ["fingerprint.transformed_attribution_unavailable", "technical_not_legal"]
    : STATUS_LIMITATIONS[status];
  const limitationIds = Array.from(new Set([...defaultLimitations, ...knownLimitations]));
  const unknownLimitationCount = (evidence.limitations?.length ?? 0) - knownLimitations.length;
  const regions = evidence.suspicious_regions;
  const copy = verificationCopy(status, evidence.algorithm_label, evidence.exact_file_hash_match);

  useGSAP(
    () => {
      if (typeof window === "undefined" || typeof window.matchMedia !== "function" || !rootRef.current) return;

      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      if (prefersReduced) {
        gsap.set(".evidence-conclusion, .evidence-facts > div, .limitation-list > li", { clearProps: "all" });
        return;
      }

      const media = gsap.matchMedia();

      media.add("(prefers-reduced-motion: no-preference)", () => {
        gsap.fromTo(
          ".evidence-conclusion",
          { autoAlpha: 0, y: 8 },
          { autoAlpha: 1, y: 0, duration: 0.32, ease: "power2.out", clearProps: "all" }
        );

        if (typeof window !== "undefined" && typeof window.matchMedia === "function" && typeof ScrollTrigger !== "undefined") {
          ScrollTrigger.create({
            trigger: rootRef.current,
            start: "top 88%",
            onEnter: () => {
              gsap.fromTo(
                ".evidence-facts > div",
                { autoAlpha: 0, y: 5 },
                { autoAlpha: 1, y: 0, duration: 0.22, stagger: 0.03, ease: "power2.out", clearProps: "all" }
              );
            },
          });
        }
      });

      return () => media.revert();
    },
    { scope: rootRef }
  );

  return (
    <article ref={rootRef} className="evidence-summary">
      <section className="evidence-conclusion" aria-label="Ý nghĩa kết quả">
        <p className="evidence-kicker">Ý nghĩa kết quả</p>
        <p>{copy.inference}</p>
      </section>
      <details className="technical-details">
        <summary>Xem chi tiết kỹ thuật</summary>
        <div className="technical-details-body">
          <section aria-labelledby="technical-data-heading">
            <h2 id="technical-data-heading">Dữ liệu kỹ thuật</h2>
            <dl className="evidence-facts">
              <div><dt>Chữ ký bảo vệ</dt><dd>{signatureLabel(evidence.manifest_signature_valid)}</dd></div>
              <div><dt>Tệp gốc</dt><dd>{hashLabel(evidence.exact_file_hash_match)}</dd></div>
              <div><dt>Số trang đã phân tích</dt><dd>{evidence.analyzed_page_count ?? "API chưa cung cấp"}</dd></div>
              <div><dt>Số phiếu hợp lệ</dt><dd>{evidence.valid_vote_count ?? "API chưa cung cấp"}</dd></div>
              <div><dt>Số vùng nghi vấn</dt><dd>{regions ? regions.length : "API chưa cung cấp"}</dd></div>
              <div><dt>Điểm fingerprint</dt><dd>{scoreLabel(evidence.fingerprint_confidence)}</dd></div>
              <div><dt>Điểm toàn vẹn</dt><dd>{scoreLabel(evidence.integrity_score)}</dd></div>
            </dl>
            <p className="evidence-absence">Chưa có ngưỡng quyết định để đánh giá các điểm là cao hay thấp.</p>
          </section>
          <section aria-labelledby="technical-limitations-heading">
            <h2 id="technical-limitations-heading">Giới hạn của kết quả</h2>
            <ul className="limitation-list">
              {limitationIds.map((id) => <li key={id}>{LIMITATION_COPY[id]}</li>)}
              {unknownLimitationCount > 0 ? <li>Kết quả có thêm giới hạn kỹ thuật chưa được giao diện mô tả chi tiết.</li> : null}
            </ul>
            <IntegrityMap regions={regions} />
          </section>
        </div>
      </details>
    </article>
  );
}
