import type { components } from "../../api/generated/schema";
import { IntegrityMap } from "./IntegrityMap";
import { LIMITATION_COPY, STATUS_COPY, STATUS_LIMITATIONS, type VerificationStatus } from "./copy";

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
  const knownLimitations = (evidence.limitations ?? []).filter((id) => id in LIMITATION_COPY);
  const limitationIds = Array.from(new Set([...STATUS_LIMITATIONS[status], ...knownLimitations]));
  const unknownLimitationCount = (evidence.limitations?.length ?? 0) - knownLimitations.length;
  const regions = evidence.suspicious_regions ?? [];

  return (
    <article className="evidence-summary">
      <section className="evidence-section" aria-labelledby="facts-heading">
        <h2 id="facts-heading">Sự kiện</h2>
        <dl className="evidence-facts">
          <div><dt>Chữ ký manifest</dt><dd>{signatureLabel(evidence.manifest_signature_valid)}</dd></div>
          <div><dt>Hash tệp chính xác</dt><dd>{hashLabel(evidence.exact_file_hash_match)}</dd></div>
          <div><dt>Số trang đã phân tích</dt><dd>{evidence.analyzed_page_count ?? "API chưa cung cấp"}</dd></div>
          <div><dt>Số phiếu hợp lệ</dt><dd>{evidence.valid_vote_count ?? "API chưa cung cấp"}</dd></div>
          <div><dt>Số vùng nghi vấn</dt><dd>{regions.length}</dd></div>
        </dl>
        <p className="evidence-absence">API không công khai mã người nhận hoặc danh tính người được phát hiện trong kết quả này.</p>
      </section>

      <section className="evidence-section" aria-labelledby="confidence-heading">
        <h2 id="confidence-heading">Độ tin cậy</h2>
        <dl className="evidence-facts">
          <div><dt>Điểm fingerprint</dt><dd>{scoreLabel(evidence.fingerprint_confidence)}</dd></div>
          <div><dt>Điểm toàn vẹn</dt><dd>{scoreLabel(evidence.integrity_score)}</dd></div>
        </dl>
        <p className="evidence-absence">API chưa cung cấp ngưỡng quyết định, vì vậy giao diện không tự đánh giá điểm là cao hay thấp.</p>
      </section>

      <section className="evidence-section" aria-labelledby="limitations-heading">
        <h2 id="limitations-heading">Giới hạn</h2>
        <ul className="limitation-list">
          {limitationIds.map((id) => <li key={id}>{LIMITATION_COPY[id]}</li>)}
          {unknownLimitationCount > 0 ? <li>Kết quả có thêm giới hạn kỹ thuật chưa được giao diện mô tả chi tiết.</li> : null}
        </ul>
        <IntegrityMap regions={regions} />
      </section>

      <section className="evidence-section" aria-labelledby="inference-heading">
        <h2 id="inference-heading">Suy luận thận trọng</h2>
        <p className="inference-label">{STATUS_COPY[status].label}</p>
        <p>{STATUS_COPY[status].inference}</p>
      </section>
    </article>
  );
}
