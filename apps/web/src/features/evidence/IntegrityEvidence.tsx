import { useState } from "react";

import { CompactIdentifier } from "../../components/CompactIdentifier";
import { downloadIssuanceManifest } from "./downloadManifest";
import type { components } from "../../api/generated/schema";
import {
  INTEGRITY_SCOPE,
  INTEGRITY_SCOPE_WITH_TRACING,
  integrityVerdict,
  type VerificationStatus,
} from "./copy";

type Attestation = components["schemas"]["ManifestAttestation"];

function comparisonLabel(
  inputSha256: string | null,
  attestation: Attestation | null,
): string {
  if (!attestation) return "Không có bản cấp phát nào để đối chiếu";
  if (!inputSha256) return "Chưa có mã băm tệp để đối chiếu";
  return inputSha256 === attestation.expected_sha256
    ? "Hai giá trị trùng nhau"
    : "Hai giá trị khác nhau";
}

function signatureText(
  signature: boolean | null | undefined,
  noSource: boolean,
): string {
  if (signature === true) return "Hợp lệ";
  if (signature === false) return "Không hợp lệ";
  if (noSource) return "Chưa kiểm tra - chưa tìm được bản cấp phát";
  return "Chưa xác minh được";
}

function issuedAtText(value: string | undefined): string | null {
  if (!value) return null;
  const parsed = new Date(value);
  if (Number.isNaN(parsed.getTime())) return value;
  return new Intl.DateTimeFormat("vi-VN", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(parsed);
}

export function IntegrityEvidence({
  status,
  evidence,
  showConclusion,
  inputSha256 = null,
  matchedIssuanceId = null,
  attestation = null,
}: {
  status: VerificationStatus;
  evidence: components["schemas"]["VerificationEvidence"];
  showConclusion: boolean;
  inputSha256?: string | null;
  matchedIssuanceId?: string | null;
  attestation?: Attestation | null;
}) {
  const [manifestError, setManifestError] = useState<string | null>(null);
  const [downloading, setDownloading] = useState(false);
  const hash = evidence.exact_file_hash_match;
  const signature = evidence.manifest_signature_valid;
  const verdict = integrityVerdict(status, hash, signature);
  const noSource = status === "NO_WATERMARK" && hash === false && signature == null;
  const issuedAt = issuedAtText(attestation?.issued_at);
  const tracingEnabled = (evidence.limitations ?? []).includes(
    "fingerprint.recall_below_release_gate",
  );
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
          <section aria-labelledby="hash-comparison-heading" className="evidence-group">
            <h2 id="hash-comparison-heading">Đối chiếu mã băm</h2>
            <p className="evidence-group-note">
              Hai giá trị dưới đây là thứ quyết định kết luận. So trực tiếp chúng
              để tự xác nhận, thay vì chỉ dựa vào dòng kết quả.
            </p>
            <dl className="evidence-facts evidence-facts-pair">
              <div>
                <dt>Mã băm tệp đã tải lên · SHA-256</dt>
                <dd>
                  {inputSha256 ? (
                    <CompactIdentifier label="Mã băm tệp đã tải lên" value={inputSha256} full />
                  ) : (
                    "Chưa có mã băm tệp đã tải lên"
                  )}
                </dd>
              </div>
              <div>
                <dt>Mã băm trong bản cấp phát đã ký · SHA-256</dt>
                <dd>
                  {attestation ? (
                    <CompactIdentifier
                      label="Mã băm trong bản cấp phát đã ký"
                      value={attestation.expected_sha256}
                      full
                    />
                  ) : (
                    "Không tìm thấy bản cấp phát có mã băm này"
                  )}
                </dd>
              </div>
              <div className="evidence-verdict-row">
                <dt>Kết quả đối chiếu</dt>
                <dd>{comparisonLabel(inputSha256, attestation)}</dd>
              </div>
            </dl>
          </section>
          <section aria-labelledby="signature-heading" className="evidence-group">
            <h2 id="signature-heading">Chữ ký số trên bản cấp phát</h2>
            <p className="evidence-group-note">
              Mã băm chỉ có giá trị nếu bản cấp phát chứa nó thật sự do đơn vị cấp
              phát ký. Khóa dưới đây là thứ toàn bộ chuỗi tin cậy dựa vào.
            </p>
            <dl className="evidence-facts">
              <div>
                <dt>Chữ ký manifest</dt>
                <dd>{signatureText(signature, noSource)}</dd>
              </div>
              {attestation ? (
                <>
                  <div>
                    <dt>Khóa ký</dt>
                    <dd>{attestation.signing_key_id}</dd>
                  </div>
                  {attestation.signing_algorithm ? (
                    <div>
                      <dt>Thuật toán ký</dt>
                      <dd>{attestation.signing_algorithm}</dd>
                    </div>
                  ) : null}
                  <div>
                    <dt>Mã băm manifest đã ký · SHA-256</dt>
                    <dd>
                      <CompactIdentifier
                        label="Mã băm manifest đã ký"
                        value={attestation.manifest_sha256}
                        full
                      />
                    </dd>
                  </div>
                  {issuedAt ? (
                    <div>
                      <dt>Thời điểm cấp phát</dt>
                      <dd>
                        <time dateTime={attestation.issued_at}>{issuedAt}</time>
                      </dd>
                    </div>
                  ) : null}
                </>
              ) : null}
              {matchedIssuanceId ? (
                <div>
                  <dt>Hồ sơ cấp phát đã khớp</dt>
                  <dd>
                    <CompactIdentifier
                      label="Hồ sơ cấp phát đã khớp"
                      value={matchedIssuanceId}
                      full
                    />
                  </dd>
                </div>
              ) : null}
            </dl>
          </section>
          {matchedIssuanceId ? (
            <section aria-labelledby="self-check-heading" className="evidence-group">
              <h2 id="self-check-heading">Cách tự kiểm chứng</h2>
              <p className="evidence-group-note">
                Kết quả này không cần được tin, nó kiểm chứng được. Băm lại tệp
                ngay trên máy rồi so với mã băm đã ký ở trên, và kiểm chữ ký bằng
                khóa công khai trong hồ sơ tải về.
              </p>
              <pre className="evidence-command" aria-label="Lệnh băm lại tệp">
                <code>certutil -hashfile &lt;tên tệp&gt; SHA256</code>
              </pre>
              <div className="evidence-export">
                <p>
                  Hồ sơ kiểm chứng gồm manifest công khai, chữ ký tách rời và khóa
                  công khai dùng để ký. Manifest này không chứa thông tin người nhận.
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
            </section>
          ) : null}
          {evidence.analyzed_page_count != null ? (
            <section aria-labelledby="processing-heading" className="evidence-group">
              <h2 id="processing-heading">Ghi nhận xử lý</h2>
              <p className="evidence-group-note">
                Số liệu về việc đọc tệp. Không tham gia vào kết luận ở trên.
              </p>
              <dl className="evidence-facts">
                <div>
                  <dt>Số trang đã đọc</dt>
                  <dd>{evidence.analyzed_page_count.toLocaleString("vi-VN")}</dd>
                </div>
              </dl>
            </section>
          ) : null}
          <section aria-labelledby="technical-limitations-heading" className="evidence-group">
            <h2 id="technical-limitations-heading">Phạm vi kiểm chứng</h2>
            <p>{tracingEnabled ? INTEGRITY_SCOPE_WITH_TRACING : INTEGRITY_SCOPE}</p>
            {extraLimits ? <p>Hồ sơ có giới hạn bổ sung. Liên hệ đơn vị cấp phát trước khi dựa vào kết quả này.</p> : null}
          </section>
        </div>
      </details>
    </article>
  );
}
