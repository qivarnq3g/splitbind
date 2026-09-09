import { expect, test, type Page, type Route } from "@playwright/test";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const UPLOAD_ID = "00000000-0000-4000-8000-000000000004";
const JOB_ID = "00000000-0000-4000-8000-000000000006";
const VERIFICATION_ID = "00000000-0000-4000-8000-000000000007";
const PDF_SHA256 = "4f1949e95440af0ece666ebd5f399c1d77d22de639950784d349fa5feb47dca5";

function response(route: Route, data: unknown, status = 200) {
  return route.fulfill({ status, contentType: "application/json", body: JSON.stringify(data) });
}

async function verificationApi(route: Route) {
  const url = new URL(route.request().url());
  if (url.pathname === "/api/v1/auth/session") return response(route, {
    authenticated: true, csrf_token: "csrf-token",
    user: { id: USER_ID, username: "verifier.demo", role: "verifier", organization_id: ORGANIZATION_ID },
  });
  if (url.pathname === "/api/v1/uploads") return response(route, {
    id: UPLOAD_ID, object_key: "uploads/orphan/verification.pdf", expected_sha256: PDF_SHA256,
    size_bytes: 14, expires_at: "2026-08-30T12:15:00Z", finalized_at: null,
    upload_url: "https://storage.example.test/direct-upload",
    required_headers: { "Content-Type": "application/pdf", "x-amz-meta-sha256": PDF_SHA256 },
  }, 201);
  if (url.pathname === `/api/v1/uploads/${UPLOAD_ID}/complete`) return response(route, {
    id: UPLOAD_ID, object_key: "uploads/orphan/verification.pdf", expected_sha256: PDF_SHA256,
    size_bytes: 14, expires_at: "2026-08-30T12:15:00Z", finalized_at: "2026-08-30T12:01:00Z",
  });
  if (url.pathname === "/api/v1/verifications") return response(route, {
    id: VERIFICATION_ID, job_id: JOB_ID, job_status: "created", status: null,
    created_at: "2026-08-30T12:01:00Z", completed_at: null, evidence: {}, metrics: {},
  }, 201);
  if (url.pathname === `/api/v1/jobs/${JOB_ID}`) return response(route, {
    id: JOB_ID, kind: "verification", status: "processing", attempt: 0,
    issuance_id: null, verification_id: VERIFICATION_ID,
    deadline_at: "2026-08-30T12:11:00Z", cancel_requested_at: null, safe_error_code: null,
    created_at: "2026-08-30T12:01:00Z", updated_at: "2026-08-30T12:02:00Z",
  });
  if (url.pathname === `/api/v1/verifications/${VERIFICATION_ID}`) return response(route, {
    id: VERIFICATION_ID, job_id: JOB_ID, job_status: "succeeded", status: "SOURCE_IDENTIFIED_MODIFIED",
    created_at: "2026-08-30T12:01:00Z", completed_at: "2026-08-30T12:03:00Z",
    evidence: {
      fingerprint_confidence: 0.75, integrity_score: 0.5, valid_vote_count: 9,
      analyzed_page_count: 3, manifest_signature_valid: true, exact_file_hash_match: false,
      suspicious_regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
      limitations: ["technical_not_legal"],
    }, metrics: { processing_ms: 25 },
  });
  return response(route, { detail: "Not found." }, 404);
}

async function mockVerifier(page: Page) {
  await page.context().addCookies([{ name: "csrftoken", value: "csrf-token", url: "http://127.0.0.1:4173" }]);
  await page.route("**/api/v1/**", verificationApi);
}

test("route motion settles and reduced motion remains immediately readable", async ({ page }, testInfo) => {
  await mockVerifier(page);
  await page.addInitScript(() => {
    const samples: string[] = [];
    Object.assign(window, { routeMotionSamples: samples });
    new MutationObserver(records => {
      for (const record of records) {
        const element = record.target;
        if (element instanceof HTMLElement && element.classList.contains("route-stage")) samples.push(element.style.opacity);
      }
    }).observe(document, { subtree: true, attributes: true, attributeFilter: ["style"] });
  });
  await page.goto("/verify");
  await expect(page.getByRole("heading", { name: "Xác minh tài liệu", exact: true })).toBeVisible();
  await expect(page.locator(".route-stage")).toHaveCSS("opacity", "1");
  const samples = await page.evaluate(() => (window as Window & { routeMotionSamples: string[] }).routeMotionSamples);
  expect(samples.some(value => Number(value) > 0 && Number(value) < 1)).toBe(true);
  await page.screenshot({ path: testInfo.outputPath("motion-settled.png"), fullPage: true });
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("/verify");
  await expect(page.getByRole("heading", { name: "Xác minh tài liệu", exact: true })).toBeVisible();
  expect(await page.locator(".route-stage").evaluate(element => element.getAttribute("style") ?? "")).not.toContain("opacity");
  await page.screenshot({ path: testInfo.outputPath("motion-reduced.png"), fullPage: true });
});

test("verification browser contract journey supports keyboard submission", async ({ page }) => {
  const workflow: string[] = [];
  await mockVerifier(page);
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (!["/api/v1/auth/session", "/api/v1/demo/capabilities"].includes(path) && (path.startsWith("/api/v1/") || path === "/direct-upload")) workflow.push(path);
  });
  await page.route("https://storage.example.test/direct-upload", async (route) => {
    expect(route.request().headers()["x-amz-meta-sha256"]).toBe(PDF_SHA256);
    expect(route.request().headers().cookie).toBeUndefined();
    await route.fulfill({ status: 200, body: "" });
  });
  await page.goto("/verify");
  await page.getByLabel("Tệp cần kiểm chứng").setInputFiles({ name: "suspect.pdf", mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF") });
  const submit = page.getByRole("button", { name: "Bắt đầu xác minh" });
  await submit.focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Đang xử lý" })).toBeVisible();
  expect(workflow.slice(0, 5)).toEqual([
    "/api/v1/uploads", "/direct-upload", `/api/v1/uploads/${UPLOAD_ID}/complete`,
    "/api/v1/verifications", `/api/v1/jobs/${JOB_ID}`,
  ]);
});

test("verification evidence keeps facts, confidence, limits, and inference separate", async ({ page }) => {
  await mockVerifier(page);
  await page.goto(`/verifications/${VERIFICATION_ID}`);
  await page.getByText("Xem chi tiết kỹ thuật", { exact: true }).click();
  for (const heading of ["Dữ liệu kỹ thuật", "Giới hạn của kết quả"]) {
    await expect(page.getByRole("heading", { name: heading })).toBeVisible();
  }
  await expect(page.getByText("API chưa cung cấp trang tương ứng và hình học từng trang", { exact: false })).toBeVisible();
  await expect(page.getByText("không chứng minh người nhận đã sửa, làm rò rỉ hoặc phát tán", { exact: false })).toBeVisible();
  await expect(page.getByText(/^Mã người nhận$/i)).toHaveCount(0);
  await expect(page.locator("svg[aria-label='Bản đồ các vùng toàn vẹn nghi vấn']")).toHaveCount(0);
});

for (const terminal of [
  { status: "failed", label: "Thất bại", safeError: "INPUT_INVALID" },
  { status: "cancelled", label: "Đã hủy", safeError: null },
] as const) {
  test(`verification job displays ${terminal.status} terminal state`, async ({ page }) => {
    await page.route("**/api/v1/**", async (route) => {
      const path = new URL(route.request().url()).pathname;
      if (path === "/api/v1/auth/session") return response(route, {
        authenticated: true, csrf_token: "csrf-token",
        user: { id: USER_ID, username: "verifier.demo", role: "verifier", organization_id: ORGANIZATION_ID },
      });
      return response(route, {
        id: JOB_ID, kind: "verification", status: terminal.status, attempt: 0,
        issuance_id: null, verification_id: VERIFICATION_ID,
        deadline_at: "2026-08-30T12:11:00Z",
        cancel_requested_at: terminal.status === "cancelled" ? "2026-08-30T12:02:00Z" : null,
        safe_error_code: terminal.safeError,
        created_at: "2026-08-30T12:01:00Z", updated_at: "2026-08-30T12:02:00Z",
      });
    });
    await page.goto(`/jobs/${JOB_ID}`);
    await expect(page.getByRole("heading", { name: terminal.label })).toBeVisible();
    await expect(page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" })).toHaveAttribute("href", `/verifications/${VERIFICATION_ID}`);
    if (terminal.safeError) await expect(page.getByRole("alert")).toContainText(terminal.safeError);
  });
}

test("verification workbench and evidence do not overflow supported widths", async ({ page }, testInfo) => {
  await mockVerifier(page);
  for (const width of [320, 375, 414, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto(width < 768 ? "/verify" : `/verifications/${VERIFICATION_ID}`);
    await expect(page.locator("main")).toBeVisible();
    const dimensions = await page.evaluate(() => ({ viewport: document.documentElement.clientWidth, scroll: document.documentElement.scrollWidth }));
    expect(dimensions.scroll, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
    await page.screenshot({ path: testInfo.outputPath(`verification-${width}.png`), fullPage: true });
  }
});
