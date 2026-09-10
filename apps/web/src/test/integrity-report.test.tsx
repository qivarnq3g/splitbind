import "@testing-library/jest-dom/vitest";
import { cleanup, render, screen } from "@testing-library/react";
import { afterEach, expect, it } from "vitest";
import { EvidenceSummary } from "../features/evidence/EvidenceSummary";
import { verificationCopy } from "../features/evidence/copy";

afterEach(cleanup);

it("keeps missing retained manifest evidence an error despite an exact hash match", () => {
  const copy = verificationCopy("INVALID_MANIFEST", "integrity_release_v1", true, null);
  expect(copy.label).toBe("Hồ sơ cấp phát không hợp lệ");
  render(<EvidenceSummary status="INVALID_MANIFEST" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: true, manifest_signature_valid: null,
  }} />);
  expect(screen.getByText("Chưa xác minh được")).toBeInTheDocument();
  expect(screen.queryByText("Hợp lệ")).not.toBeInTheDocument();
});

it("reports no matching issuance without claiming a known document was modified", () => {
  render(<EvidenceSummary status="NO_WATERMARK" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: false,
    manifest_signature_valid: null, analyzed_page_count: 1,
    fingerprint_confidence: 0, valid_vote_count: 0, integrity_score: null,
  }} />);
  expect(screen.getByText(/Không tìm thấy bản cấp phát có mã SHA-256 trùng/)).toBeVisible();
  expect(screen.getByText("Chưa kiểm tra — chưa tìm được bản cấp phát")).toBeInTheDocument();
  expect(document.body).not.toHaveTextContent(/API|Số phiếu|Điểm fingerprint|Điểm toàn vẹn|Vùng toàn vẹn nghi vấn/);
});

it("keeps an unavailable signature distinct from one not checked because no match exists", () => {
  render(<EvidenceSummary status="PARTIAL_EVIDENCE" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: true,
    manifest_signature_valid: null,
  }} />);
  expect(screen.getByText("Chưa xác minh được")).toBeInTheDocument();
  expect(screen.queryByText(/chưa tìm được bản cấp phát/)).not.toBeInTheDocument();
});

it("does not claim intact integrity from a successful status with absent signature evidence", () => {
  const copy = verificationCopy("VERIFIED_INTACT", "integrity_release_v1", true, null);
  expect(copy.label).toBe("Chưa đủ bằng chứng xác minh");
});

it("requires both exact hash and valid signature for a production success", () => {
  const copy = verificationCopy("VERIFIED_INTACT", "integrity_release_v1", true, true);
  expect(copy.label).toBe("Tệp khớp bản cấp phát");
  expect(copy.inference).toContain("chữ ký");
});

it.each(["PROCESSING_FAILED", "INVALID_MANIFEST"] as const)("preserves %s instead of reporting a mismatch", (status) => {
  const copy = verificationCopy(status, "integrity_release_v1", false, null);
  expect(copy.label).not.toMatch(/khớp|nguyên vẹn/i);
});

it("does not describe partial evidence as decoded watermark in integrity mode", () => {
  const copy = verificationCopy("PARTIAL_EVIDENCE", "integrity_release_v1", true, null);
  expect(copy.label).toBe("Chưa đủ bằng chứng xác minh");
  expect(copy.inference).not.toMatch(/watermark|thủy vân/);
});
