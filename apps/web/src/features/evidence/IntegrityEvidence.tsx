import { useState } from "react";

import { CompactIdentifier } from "../../components/CompactIdentifier";
import { downloadIssuanceManifest } from "./downloadManifest";
import type { components } from "../../api/generated/schema";
import { INTEGRITY_SCOPE, integrityVerdict, type VerificationStatus } from "./copy";

export function IntegrityEvidence({
  status,
  evidence,
  showConclusion,
  inputSha256 = null,
  matchedIssuanceId = null,
}: {
  status: VerificationStatus;
  evidence: components["schemas"]["VerificationEvidence"];
  showConclusion: boolean;
  inputSha256?: string | null;
  matchedIssuanceId?: string | null;
}) {
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
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
              {matchedIssuanceId ? <div><dt>Hồ sơ cấp phát đã khớp</dt><dd><CompactIdentifier label="Hồ sơ cấp phát đã khớp" value={matchedIssuanceId} full /></dd></div> : null}
            </dl>
            {matchedIssuanceId ? (
              <div className="evidence-export">
                <p>
                  Tải hồ sơ kiểm chứng để tự đối chiếu bằng công cụ khác. Tệp gồm
                  bản kê khai công khai, chữ ký tách rời và khóa công khai dùng để
                  ký. Bản kê khai này không chứa thông tin người nhận.
                </p>
                <button
                  className="button button-secondary"
                  type="button"
                  disabled={downloading}
                  onClick={() => {
                    setManifestError(null);
                    setDownloading(true);
                    downloadIssuanceManifest(matchedIssuanceId)
                      .catch((error: unknown) => {
                        setManifestError(
                          error instanceof Error
                            ? error.message
                            : "Không tải được hồ sơ kiểm chứng.",
                        );
                      })
                      .finally(() => setDownloading(false));
                  }}
                >
                  {downloading ? "Đang tải hồ sơ" : "Tải hồ sơ kiểm chứng"}
                </button>
                {manifestError ? (
                  <p className="form-error" role="alert">{manifestError}</p>
                ) : null}
              </div>
            ) : null}
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
