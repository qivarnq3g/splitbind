import { chromium, expect } from "@playwright/test";
import { mkdir, readFile } from "node:fs/promises";
import { resolve } from "node:path";

const origin = process.env.SMOKE_ORIGIN ?? "https://splitbind.qivarn.id.vn";
const output = resolve("../../artifacts/real-downloads-smoke");
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

  // 2. Test rejection of > 10 MiB PDF: 'Bài tập thuyết trình - Nhóm 10.pdf' (14.8 MiB)
  const oversizedPath = "C:/Users/Qivarn/Downloads/Bài tập thuyết trình - Nhóm 10.pdf";
  await page.getByLabel("Tệp PDF", { exact: true }).setInputFiles(oversizedPath);
  await expect(page.locator(".field-help-error")).toContainText("vượt quá giới hạn 10 MiB");
  await page.screenshot({ path: `${output}/01_oversized_rejected.png`, fullPage: true });
  console.log("OVERSIZED_PDF_REJECTED_AS_EXPECTED");

  // 3. Test that /issue input does NOT accept images
  const samplePngPath = resolve(output, "transcript_sample.png");
  await page.getByLabel("Tệp PDF", { exact: true }).setInputFiles(samplePngPath);
  await expect(page.locator(".field-help-error")).toContainText("không phải PDF");
  await page.screenshot({ path: `${output}/02_issue_png_rejected.png`, fullPage: true });
  console.log("ISSUE_PAGE_REJECTS_IMAGE_AS_EXPECTED");

  // 4. Test real PDF 1: University_of_Maryland_Global_Campus_Transcript.pdf (13 KiB)
  const transcriptPath = "C:/Users/Qivarn/Downloads/University_of_Maryland_Global_Campus_Transcript.pdf";
  await page.getByLabel("Tệp PDF", { exact: true }).setInputFiles(transcriptPath);
  const email1 = `umgc.student.${Date.now()}@example.edu`;
  await page.getByLabel("Email người nhận", { exact: true }).fill(email1);
  await page.getByLabel("Họ và tên", { exact: true }).fill("UMGC Student");
  const issueResp1Promise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/issuances` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Tạo bản cấp phát", exact: true }).click();
  const issueResp1 = await issueResp1Promise;
  expect(issueResp1.status()).toBe(201);
  const issuance1 = await issueResp1.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ cấp phát" }).click();
  await expect(page.getByRole("heading", { name: "Bản cấp phát đã sẵn sàng" })).toBeVisible();
  await page.screenshot({ path: `${output}/03_transcript_issued.png`, fullPage: true });
  console.log("TRANSCRIPT_ISSUED_SUCCESSFULLY", issuance1.id);

  // Download issued transcript PDF
  let download1;
  await page.route(`**/issuances/${issuance1.id}/result`, async route => {
    const response = await route.fetch();
    download1 = await response.json();
    await route.fulfill({ response });
  });
  const resultResp1 = page.waitForResponse(resp => resp.url().endsWith(`/issuances/${issuance1.id}/result`));
  await page.getByRole("button", { name: "Tải PDF kết quả", exact: true }).click();
  expect((await resultResp1).status()).toBe(200);
  const artifact1 = await context.request.get(download1.download_url);
  expect(artifact1.status()).toBe(200);
  const issuedTranscriptBytes = await artifact1.body();

  // 5. Verify the issued transcript PDF on /verify -> expects VERIFIED_INTACT
  await page.goto(`${origin}/verify`);
  await page.getByLabel("Tệp cần kiểm chứng", { exact: true }).setInputFiles({
    name: "issued-transcript.pdf",
    mimeType: "application/pdf",
    buffer: issuedTranscriptBytes,
  });
  const verifyResp1Promise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/verifications` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
  const verifyResp1 = await verifyResp1Promise;
  expect(verifyResp1.status()).toBe(201);
  const verification1 = await verifyResp1.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" }).click();
  await expect(page.getByRole("heading", { name: "Tệp khớp bản cấp phát", exact: true })).toBeVisible();
  await page.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Bằng chứng đối chiếu" })).toBeVisible();
  await page.screenshot({ path: `${output}/04_transcript_verified_intact.png`, fullPage: true });

  const check1 = await context.request.get(`${origin}/api/v1/verifications/${verification1.id}`);
  const result1 = await check1.json();
  expect(result1.status).toBe("VERIFIED_INTACT");
  expect(result1.evidence.exact_file_hash_match).toBe(true);
  expect(result1.evidence.manifest_signature_valid).toBe(true);
  console.log("TRANSCRIPT_VERIFIED_INTACT_PASSED");

  // 6. Test Image Verification on /verify (chứng minh /verify chấp nhận ảnh PNG)
  await page.goto(`${origin}/verify`);
  const pngBytes = await readFile(samplePngPath);
  await page.getByLabel("Tệp cần kiểm chứng", { exact: true }).setInputFiles({
    name: "transcript-page1.png",
    mimeType: "image/png",
    buffer: pngBytes,
  });
  const verifyImagePromise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/verifications` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
  const verifyImageResp = await verifyImagePromise;
  expect(verifyImageResp.status()).toBe(201);
  const imageVerification = await verifyImageResp.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" }).click();
  await expect(page.getByRole("heading", { name: "Chưa tìm thấy bản cấp phát khớp", exact: true })).toBeVisible();
  await page.locator("summary").focus();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("heading", { name: "Bằng chứng đối chiếu" })).toBeVisible();
  await page.screenshot({ path: `${output}/05_image_verified_unmatched.png`, fullPage: true });

  const checkImg = await context.request.get(`${origin}/api/v1/verifications/${imageVerification.id}`);
  const resultImg = await checkImg.json();
  expect(resultImg.status).toBe("NO_WATERMARK");
  expect(resultImg.evidence.exact_file_hash_match).toBe(false);
  expect(resultImg.evidence.manifest_signature_valid).toBe(null);
  console.log("IMAGE_VERIFICATION_ACCEPTED_AND_PROCESSED_PASSED");

  // 7. Test real PDF 2: N03_Nhom9.pdf (355 KiB)
  await page.goto(`${origin}/issue`);
  const nhom9Path = "C:/Users/Qivarn/Downloads/N03_Nhom9.pdf";
  await page.getByLabel("Tệp PDF", { exact: true }).setInputFiles(nhom9Path);
  const email2 = `nhom9.recipient.${Date.now()}@example.com`;
  await page.getByLabel("Email người nhận", { exact: true }).fill(email2);
  await page.getByLabel("Họ và tên", { exact: true }).fill("Nhóm 9 An Toàn Thông Tin");
  const issueResp2Promise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/issuances` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Tạo bản cấp phát", exact: true }).click();
  const issueResp2 = await issueResp2Promise;
  expect(issueResp2.status()).toBe(201);
  const issuance2 = await issueResp2.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ cấp phát" }).click();
  await page.screenshot({ path: `${output}/06_nhom9_issued.png`, fullPage: true });
  console.log("NHOM9_PDF_ISSUED_SUCCESSFULLY", issuance2.id);

  // Download issued nhom9 PDF
  let download2;
  await page.route(`**/issuances/${issuance2.id}/result`, async route => {
    const response = await route.fetch();
    download2 = await response.json();
    await route.fulfill({ response });
  });
  const resultResp2 = page.waitForResponse(resp => resp.url().endsWith(`/issuances/${issuance2.id}/result`));
  await page.getByRole("button", { name: "Tải PDF kết quả", exact: true }).click();
  expect((await resultResp2).status()).toBe(200);
  const artifact2 = await context.request.get(download2.download_url);
  expect(artifact2.status()).toBe(200);
  const issuedNhom9Bytes = await artifact2.body();

  // Verify issued nhom9 PDF
  await page.goto(`${origin}/verify`);
  await page.getByLabel("Tệp cần kiểm chứng", { exact: true }).setInputFiles({
    name: "issued-nhom9.pdf",
    mimeType: "application/pdf",
    buffer: issuedNhom9Bytes,
  });
  const verifyResp2Promise = page.waitForResponse(resp => resp.url() === `${origin}/api/v1/verifications` && resp.request().method() === "POST");
  await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
  const verifyResp2 = await verifyResp2Promise;
  expect(verifyResp2.status()).toBe(201);
  const verification2 = await verifyResp2.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" }).click();
  await expect(page.getByRole("heading", { name: "Tệp khớp bản cấp phát", exact: true })).toBeVisible();
  await page.screenshot({ path: `${output}/07_nhom9_verified_intact.png`, fullPage: true });

  const check2 = await context.request.get(`${origin}/api/v1/verifications/${verification2.id}`);
  const result2 = await check2.json();
  expect(result2.status).toBe("VERIFIED_INTACT");
  expect(result2.evidence.exact_file_hash_match).toBe(true);
  expect(result2.evidence.manifest_signature_valid).toBe(true);
  console.log("NHOM9_VERIFIED_INTACT_PASSED");

  // 8. Logout
  await page.getByRole("button", { name: "Đăng xuất khỏi SplitBind" }).click();
  await expect(page.getByRole("heading", { name: "Đăng nhập SplitBind" })).toBeVisible();
  console.log("LOGOUT_SUCCESS");

  expect(errors).toEqual([]);
  console.log("ALL_REAL_DOWNLOADS_TESTS_PASSED");

} finally {
  await context.close();
  await browser.close();
}
