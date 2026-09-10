import { chromium, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const origin = process.env.SMOKE_ORIGIN ?? "https://splitbind.qivarn.id.vn";
const output = resolve("../../artifacts/attack-scenarios");
await mkdir(output, { recursive: true });

const browser = await chromium.launch();
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });

try {
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", err => errors.push(err.message));
  page.on("console", msg => { if (msg.type() === "error") errors.push(msg.text()); });

  // 1. Log in
  await page.goto(`${origin}/login`);
  await page.getByLabel("Tên đăng nhập", { exact: true }).fill("phuc");
  await page.getByLabel("Mật khẩu", { exact: true }).fill("123");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL("**/issue");
  console.log("LOGIN_SUCCESS");

  // Helper function to run verification on a file
  async function runVerification(filePath, filename, screenshotName, testCaseName) {
    await page.goto(`${origin}/verify`);
    const fileBytes = await readFile(filePath);
    await page.getByLabel("Tệp cần kiểm chứng", { exact: true }).setInputFiles({
      name: filename,
      mimeType: "application/pdf",
      buffer: fileBytes,
    });
    const verifyRespPromise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/verifications` && resp.request().method() === "POST");
    await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
    const verifyResp = await verifyRespPromise;
    expect(verifyResp.status()).toBe(201);
    const verification = await verifyResp.json();
    await expect(page.getByRole("heading", { name: /Hoàn tất|Thất bại/ })).toBeVisible({ timeout: 120000 });
    const openLink = page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" });
    if (await openLink.count() > 0) {
      await openLink.click();
    }
    
    // Open summary accordion if present
    const summary = page.locator("summary");
    if (await summary.count() > 0) {
      await summary.focus();
      await page.keyboard.press("Enter");
    }
    
    await page.screenshot({ path: `${output}/${screenshotName}`, fullPage: true });

    // Fetch API details directly via page evaluate inside authenticated browser
    const result = await page.evaluate(async (url) => {
      const resp = await fetch(url, { credentials: "include" });
      if (!resp.ok) throw new Error(`Fetch ${url} failed with ${resp.status}`);
      return await resp.json();
    }, `${origin}/api/v1/verifications/${verification.id}`);
    console.log(`CASE_${testCaseName}:`, JSON.stringify({
      status: result.status,
      exact_hash_match: result.evidence?.exact_file_hash_match,
      manifest_signature_valid: result.evidence?.manifest_signature_valid,
      algorithm: result.evidence?.algorithm_label,
    }));
    return result;
  }

  // 2. Issue genuine Transcript PDF (1 page) as baseline
  const transcriptPath = "C:/Users/Qivarn/Downloads/University_of_Maryland_Global_Campus_Transcript.pdf";
  await page.goto(`${origin}/issue`);
  await page.getByLabel("Tệp PDF", { exact: true }).setInputFiles(transcriptPath);
  const emailTranscript = `transcript.baseline.${Date.now()}@example.edu`;
  await page.getByLabel("Email người nhận", { exact: true }).fill(emailTranscript);
  await page.getByLabel("Họ và tên", { exact: true }).fill("UMGC Transcript Genuine");
  const issueRespPromise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/issuances` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Tạo bản cấp phát", exact: true }).click();
  const issueResp = await issueRespPromise;
  expect(issueResp.status()).toBe(201);
  const issuance = await issueResp.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ cấp phát" }).click();
  
  let download;
  await page.route(`**/issuances/${issuance.id}/result`, async route => {
    const response = await route.fetch();
    download = await response.json();
    await route.fulfill({ response });
  });
  const resultResp = page.waitForResponse(resp => resp.url().endsWith(`/issuances/${issuance.id}/result`));
  await page.getByRole("button", { name: "Tải PDF kết quả", exact: true }).click();
  expect((await resultResp).status()).toBe(200);
  const artifact = await context.request.get(download.download_url);
  expect(artifact.status()).toBe(200);
  const genuineTranscriptBytes = await artifact.body();

  // Test baseline genuine verification -> VERIFIED_INTACT
  await page.goto(`${origin}/verify`);
  await page.getByLabel("Tệp cần kiểm chứng", { exact: true }).setInputFiles({
    name: "genuine-transcript.pdf",
    mimeType: "application/pdf",
    buffer: genuineTranscriptBytes,
  });
  const verifyBaselinePromise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/verifications` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
  const verifyBaselineResp = await verifyBaselinePromise;
  expect(verifyBaselineResp.status()).toBe(201);
  const baselineVer = await verifyBaselineResp.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" }).click();
  await expect(page.getByRole("heading", { name: "Tệp khớp bản cấp phát", exact: true })).toBeVisible();
  await page.screenshot({ path: `${output}/00_baseline_genuine_intact.png`, fullPage: true });
  console.log("BASELINE_GENUINE_VERIFIED_INTACT_PASSED");

  // Attack 1: Trailing Byte Injection (sửa đổi byte / chèn mã độc đuôi)
  const r1 = await runVerification(
    resolve(output, "attack_1_byte_injection.pdf"),
    "attack_1_byte_injection.pdf",
    "01_byte_injection_unmatched.png",
    "1_BYTE_INJECTION"
  );
  expect(r1.status).toBe("NO_WATERMARK");
  expect(r1.evidence.exact_file_hash_match).toBe(false);

  // Attack 2: Visual Tampering (chèn che đậy, sửa text điểm giả mạo)
  const r2 = await runVerification(
    resolve(output, "attack_2_visual_tampering.pdf"),
    "attack_2_visual_tampering.pdf",
    "02_visual_tampering_unmatched.png",
    "2_VISUAL_TAMPERING"
  );
  expect(r2.status).toBe("NO_WATERMARK");
  expect(r2.evidence.exact_file_hash_match).toBe(false);

  // Attack 3: Page Truncation (xóa 10/11 trang của tài liệu)
  const r3 = await runVerification(
    resolve(output, "attack_3_page_truncated.pdf"),
    "attack_3_page_truncated.pdf",
    "03_page_truncated_unmatched.png",
    "3_PAGE_TRUNCATION"
  );
  expect(r3.status).toBe("NO_WATERMARK");
  expect(r3.evidence.exact_file_hash_match).toBe(false);

  // Attack 4: Alien / Unissued Document (tài liệu ngoại lai hợp lệ 1 trang chưa từng được cấp phát)
  const unissuedPath = "C:/Users/Qivarn/Downloads/Nh\u00e0 N\u01b0\u1edbc X\u00e3 H\u1ed9i Ch\u1ee7 Ngh\u0129a.pdf";
  const r4 = await runVerification(
    unissuedPath,
    "Nha_Nuoc_Xa_Hoi_Chu_Nghia.pdf",
    "04_unissued_document_unmatched.png",
    "4_UNISSUED_DOCUMENT"
  );
  expect(r4.status).toBe("NO_WATERMARK");
  expect(r4.evidence.exact_file_hash_match).toBe(false);

  // Attack 5: Resource Limit Defense (tài liệu vượt quá giới hạn 5 trang demo: Glossary 15 trang)
  const r5 = await runVerification(
    "C:/Users/Qivarn/Downloads/Glossary_Tong_Hop.pdf",
    "Glossary_Tong_Hop.pdf",
    "05_page_limit_defense.png",
    "5_PAGE_LIMIT_DEFENSE"
  );
  expect(r5.status).toBe("PROCESSING_FAILED");
  console.log("CASE_5_PAGE_LIMIT_DEFENSE_PASSED:", r5.status);

  // Attack 6: Malformed / Binary Corrupted PDF Structure
  const r6 = await runVerification(
    resolve(output, "attack_5_malformed_corrupted.pdf"),
    "attack_5_malformed_corrupted.pdf",
    "06_malformed_pdf_handled.png",
    "6_MALFORMED_PDF"
  );
  expect(r6.status).toBe("PROCESSING_FAILED");
  console.log("CASE_6_MALFORMED_HANDLED_SAFELY:", r6.status);

  // 6. Direct API Security Attacks
  console.log("TESTING_DIRECT_API_SECURITY_CONTROLS...");
  
  // Attack 6a: POST /api/v1/verifications without CSRF token
  const unauthApi = await (await chromium.launch()).newContext();
  const csrfAttackResp = await unauthApi.request.post(`${origin}/api/v1/verifications`, {
    data: { upload_id: "00000000-0000-4000-8000-000000000001" },
  });
  console.log("API_ATTACK_NO_CSRF_STATUS:", csrfAttackResp.status());
  expect([401, 403]).toContain(csrfAttackResp.status());

  // Attack 6b: POST with non-existent upload_id
  const nonExistentUploadStatus = await page.evaluate(async () => {
    const sess = await (await fetch("/api/v1/auth/session", { credentials: "include" })).json();
    const r = await fetch("/api/v1/verifications", {
      method: "POST",
      credentials: "include",
      headers: {
        "Content-Type": "application/json",
        "X-CSRFToken": sess.csrf_token,
      },
      body: JSON.stringify({ upload_id: "00000000-0000-4000-8000-000000000000" }),
    });
    return r.status;
  });
  console.log("API_ATTACK_NONEXISTENT_UPLOAD_STATUS:", nonExistentUploadStatus);
  expect([400, 404]).toContain(nonExistentUploadStatus);
  await unauthApi.close();

  // 7. Healthcheck verification
  const healthResult = await page.evaluate(async () => {
    const r = await fetch("/health/live");
    return { status: r.status, body: await r.json() };
  });
  expect(healthResult.status).toBe(200);
  expect(healthResult.body.status).toBe("ok");
  console.log("WORKER_AND_SYSTEM_HEALTH_LIVE_VERIFIED:", JSON.stringify(healthResult.body));

  await page.getByRole("button", { name: "Đăng xuất khỏi SplitBind" }).click();
  await expect(page.getByRole("heading", { name: "Đăng nhập SplitBind" })).toBeVisible();
  console.log("ALL_ATTACK_SCENARIOS_TESTED_SUCCESSFULLY");

} finally {
  await context.close();
  await browser.close();
}
