import "@testing-library/jest-dom/vitest";
import { cleanup, fireEvent, render, screen } from "@testing-library/react";
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
  expect(screen.getByText("Chưa kiểm tra - chưa tìm được bản cấp phát")).toBeInTheDocument();
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

it("renders the uploaded file's own digest in the technical panel", () => {
  const digest = "1234567890abcdef".repeat(4);
  render(<EvidenceSummary status="NO_WATERMARK" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: false,
    manifest_signature_valid: null,
  }} inputSha256={digest} />);
  expect(screen.getByText("Mã băm tệp đã tải lên · SHA-256")).toBeInTheDocument();
  expect(screen.getByText(digest)).toBeInTheDocument();
});

it("states explicitly that no digest exists yet instead of an empty cell", () => {
  render(<EvidenceSummary status="NO_WATERMARK" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: false,
    manifest_signature_valid: null,
  }} inputSha256={null} />);
  expect(screen.getByText("Chưa có mã băm tệp đã tải lên")).toBeInTheDocument();
});

const DIGEST = "1234567890abcdef".repeat(4);
const ATTESTATION = {
  expected_sha256: DIGEST,
  manifest_sha256: "c".repeat(64),
  issued_at: "2026-08-30T00:00:00Z",
  signing_key_id: "key-prod-1",
  signing_algorithm: "Ed25519",
  integrity_algorithm: "integrity-v1",
};

function openDisclosure() {
  fireEvent.click(screen.getByText("Xem chi tiết kỹ thuật"));
}

function renderMatched(attestation: typeof ATTESTATION | null = ATTESTATION) {
  render(<EvidenceSummary status="VERIFIED_INTACT" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: true,
    manifest_signature_valid: true,
  }} inputSha256={DIGEST} matchedIssuanceId="6172004d-7953-4b17-bee0-3b365fc29648"
     attestation={attestation} />);
  openDisclosure();
}

it("puts the signed hash beside the uploaded one so a reader compares them", () => {
  renderMatched();

  expect(screen.getByText("Mã băm tệp đã tải lên · SHA-256")).toBeInTheDocument();
  expect(screen.getByText("Mã băm trong bản cấp phát đã ký · SHA-256")).toBeInTheDocument();
  expect(screen.getAllByText(DIGEST)).toHaveLength(2);
  expect(screen.getByText("Hai giá trị trùng nhau")).toBeVisible();
});

it("names the key and the exact bytes the signature covers", () => {
  renderMatched();

  expect(screen.getByText("key-prod-1")).toBeInTheDocument();
  expect(screen.getByText("Ed25519")).toBeInTheDocument();
  expect(screen.getByText(ATTESTATION.manifest_sha256)).toBeInTheDocument();
});

it("says there is nothing to compare rather than implying a comparison happened", () => {
  render(<EvidenceSummary status="NO_WATERMARK" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: false,
    manifest_signature_valid: null,
  }} inputSha256={DIGEST} attestation={null} />);
  openDisclosure();

  expect(screen.getByText("Không có bản cấp phát nào để đối chiếu")).toBeVisible();
  expect(screen.queryByText("Hai giá trị trùng nhau")).not.toBeInTheDocument();
  expect(screen.queryByText("Hai giá trị khác nhau")).not.toBeInTheDocument();
});

it("keeps the page count out of the facts the verdict rests on", () => {
  render(<EvidenceSummary status="VERIFIED_INTACT" evidence={{
    algorithm_label: "integrity_release_v1", exact_file_hash_match: true,
    manifest_signature_valid: true, analyzed_page_count: 5,
  }} inputSha256={DIGEST} attestation={ATTESTATION} />);
  openDisclosure();

  const comparison = screen.getByRole("heading", { name: "Đối chiếu mã băm" })
    .closest("section")!;
  expect(comparison).not.toHaveTextContent("Số trang đã đọc");
  const processing = screen.getByRole("heading", { name: "Ghi nhận xử lý" })
    .closest("section")!;
  expect(processing).toHaveTextContent("Số trang đã đọc");
  expect(processing).toHaveTextContent("Không tham gia vào kết luận");
});

it("tells the reader how to repeat the check outside the app", () => {
  renderMatched();

  expect(screen.getByRole("heading", { name: "Cách tự kiểm chứng" })).toBeVisible();
  expect(screen.getByText(/certutil -hashfile/)).toBeVisible();
  expect(screen.getByRole("button", { name: "Tải hồ sơ kiểm chứng" })).toBeVisible();
});
