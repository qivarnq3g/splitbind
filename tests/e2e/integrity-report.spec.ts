import { expect, test } from "@playwright/test";

const recordId = "00000000-0000-4000-8000-000000000007";
const inputDigest = "1234567890abcdef".repeat(4);
const manifestDigest = "fedcba0987654321".repeat(4);
const cases = [
  { name: "unmatched", status: "NO_WATERMARK", hash: false, signature: null, title: "Chưa tìm thấy bản cấp phát khớp", tone: "warning" },
  { name: "intact", status: "VERIFIED_INTACT", hash: true, signature: true, title: "Tệp khớp bản cấp phát", tone: "success" },
  { name: "incomplete", status: "VERIFIED_INTACT", hash: true, signature: null, title: "Chưa đủ bằng chứng xác minh", tone: "warning" },
  { name: "ambiguous", status: "PARTIAL_EVIDENCE", hash: true, signature: null, title: "Chưa đủ bằng chứng xác minh", tone: "warning" },
  { name: "invalid", status: "INVALID_MANIFEST", hash: true, signature: false, title: "Hồ sơ cấp phát không hợp lệ", tone: "error" },
  { name: "missing-manifest", status: "INVALID_MANIFEST", hash: true, signature: null, title: "Hồ sơ cấp phát không hợp lệ", tone: "error" },
  { name: "failed", status: "PROCESSING_FAILED", hash: null, signature: null, title: "Xử lý thất bại", tone: "error" },
] as const;

for (const scenario of cases) {
  test(`production evidence report: ${scenario.name}`, async ({ page }, testInfo) => {
    const errors: string[] = [];
    page.on("pageerror", error => errors.push(error.message));
    page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
    await page.route("**/api/v1/**", async route => {
      const path = new URL(route.request().url()).pathname;
      const data = path.endsWith("/auth/session") ? {
        authenticated: true, csrf_token: "fixture",
        user: { id: recordId, username: "review.operator", role: "administrator", organization_id: recordId },
      } : path.endsWith("/demo/capabilities") ? {
        enabled: true, algorithm_label: "integrity_release_v1",
      } : {
        id: recordId, job_id: recordId, job_status: scenario.name === "failed" ? "failed" : "succeeded",
        status: scenario.status, created_at: "2026-09-09T12:00:00Z", completed_at: "2026-09-09T12:00:05Z",
        evidence: {
          algorithm_label: "integrity_release_v1", decode_status: scenario.hash ? "decoded" : "payload_not_detected",
          exact_file_hash_match: scenario.hash, manifest_signature_valid: scenario.signature,
          analyzed_page_count: 1, fingerprint_confidence: 0, valid_vote_count: 0, integrity_score: null,
          limitations: ["evidence.not_proof_of_leak_edit_or_distribution", "fingerprint.transformed_attribution_unavailable"],
        },
        input_sha256: inputDigest,
        matched_issuance_id: scenario.hash ? recordId : null,
        attestation: scenario.hash
          ? {
              expected_sha256: inputDigest,
              manifest_sha256: manifestDigest,
              issued_at: "2026-09-09T11:59:00Z",
              signing_key_id: "key-integrity-1",
              signing_algorithm: "Ed25519",
              integrity_algorithm: "integrity-v1",
            }
          : null,
        metrics: { processing_ms: 5000 },
      };
      await route.fulfill({ json: data });
    });
    const sizes = scenario.name === "unmatched" || scenario.name === "intact"
      ? [[1920, 1080], [1280, 800], [768, 1024], [375, 667], [320, 667], [414, 896]]
      : [[1280, 800], [375, 667]];
    for (const [width, height] of sizes) {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: width <= 414 ? "reduce" : "no-preference" });
      await page.goto(`/verifications/${recordId}`);
      const verdict = page.getByRole("region", { name: "Kết luận kiểm chứng" });
      await expect(verdict.getByRole("heading", { name: scenario.title })).toBeVisible();
      await expect(verdict).toHaveAttribute("data-tone", scenario.tone);
      const summary = page.locator("summary");
      await expect(page.locator("details")).not.toHaveAttribute("open");
      await summary.focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { name: "Đối chiếu mã băm" })).toBeVisible();
      await expect(page.getByText("Mã băm tệp đã tải lên · SHA-256")).toBeVisible();
      await expect(page.getByText("Mã băm trong bản cấp phát đã ký · SHA-256")).toBeVisible();
      if (scenario.hash) {
        await expect(page.getByText("Hai giá trị trùng nhau")).toBeVisible();
        await expect(page.getByText("key-integrity-1")).toBeVisible();
      } else {
        await expect(page.getByText("Không có bản cấp phát nào để đối chiếu")).toBeVisible();
      }
      await expect(page.locator("main")).not.toContainText(/API|Số phiếu|Điểm fingerprint|Điểm toàn vẹn|Vùng toàn vẹn nghi vấn/);
      await expect(page.getByRole("complementary", { name: "Giới hạn chế độ demo" })).toHaveCount(0);
      await expect(page.getByRole("complementary", { name: "Khả năng xác minh" })).toHaveCount(0);
      if (scenario.name === "unmatched") await expect(page.getByText("Chưa kiểm tra - chưa tìm được bản cấp phát")).toBeVisible();
      await expect(page.locator(".route-stage")).toHaveCSS("opacity", "1");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: testInfo.outputPath(`${scenario.name}-${width}.png`), fullPage: true });
    }
    await page.getByRole("link", { name: "Kiểm tra tệp khác" }).click();
    await expect(page).toHaveURL(/\/verify$/);
    expect(errors).toEqual([]);
  });
}
