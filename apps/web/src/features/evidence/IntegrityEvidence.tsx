import { CompactIdentifier } from "../../components/CompactIdentifier";
import type { components } from "../../api/generated/schema";
import { INTEGRITY_SCOPE, integrityVerdict, type VerificationStatus } from "./copy";

export function IntegrityEvidence({ status, evidence, showConclusion, inputSha256 = null }: {
  status: VerificationStatus;
  evidence: components["schemas"]["VerificationEvidence"];
  showConclusion: boolean;
  inputSha256?: string | null;
}) {
  const hash = evidence.exact_file_hash_match;
  const signature = evidence.manifest_signature_valid;
  const verdict = integrityVerdict(status, hash, signature);
  const noSource = status === "NO_WATERMARK" && hash === false && signature == null;
  const extraLimits = (evidence.limitations ?? []).some(id => ![
    "evidence.not_proof_of_leak_edit_or_distribution",
    "fingerprint.transformed_attribution_unavailable",
    "fingerprint.recall_below_release_gate",
    "match_not_actor_proof", "technical_not_legal",
  ].includes(id));
  return (
    <article className="evidence-summary integrity-evidence">
      {showConclusion ? <p>{verdict.inference}</p> : null}
      <details className="technical-details">
        <summary>Xem chi tiết kỹ thuật</summary>
        <div className="technical-details-body">
          <section aria-labelledby="technical-data-heading">
            <h2 id="technical-data-heading">Bằng chứng đối chiếu</h2>
            <dl className="evidence-facts">
              <div><dt>Mã băm tệp đã tải lên · SHA-256</dt><dd>{inputSha256 ? <CompactIdentifier label="Mã băm tệp đã tải lên" value={inputSha256} full /> : "Chưa có mã băm tệp đã tải lên"}</dd></div>
              <div><dt>Thuật toán xử lý</dt><dd>{evidence.algorithm_label ?? "Chưa có thông tin thuật toán"}</dd></div>
              <div><dt>Mã kiểm tra tệp · SHA-256</dt><dd>{hash === true ? "Khớp bản cấp phát" : hash === false ? "Không tìm thấy bản khớp" : "Chưa có kết quả đối chiếu"}</dd></div>
              <div><dt>Chữ ký hồ sơ cấp phát</dt><dd>{signature === true ? "Hợp lệ" : signature === false ? "Không hợp lệ" : noSource ? "Chưa kiểm tra - chưa tìm được bản cấp phát" : "Chưa xác minh được"}</dd></div>
              {evidence.analyzed_page_count != null ? <div><dt>Số trang đã đọc</dt><dd>{evidence.analyzed_page_count.toLocaleString("vi-VN")}</dd></div> : null}
            </dl>
          </section>
          <section aria-labelledby="technical-limitations-heading">
            <h2 id="technical-limitations-heading">Phạm vi kiểm chứng</h2>
            <p>{INTEGRITY_SCOPE}</p>
            {extraLimits ? <p>Hồ sơ có giới hạn bổ sung. Liên hệ đơn vị cấp phát trước khi dựa vào kết quả này.</p> : null}
          </section>
        </div>
      </details>
    </article>
  );
}
