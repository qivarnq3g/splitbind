import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";
import { resolve } from "node:path";

const required = ["SMOKE_ORIGIN", "SMOKE_USERNAME", "SMOKE_PASSWORD", "SMOKE_RECIPIENT_ID"];
if (process.env.SMOKE_ALLOW_WRITES !== "1" || required.some(key => !process.env[key])) {
  throw new Error("Set SMOKE_ALLOW_WRITES=1 and all SMOKE_ORIGIN/USERNAME/PASSWORD/RECIPIENT_ID variables. This creates synthetic issuance and verification records.");
}
const origin = new URL(process.env.SMOKE_ORIGIN).origin;
if (!origin.startsWith("https://")) throw new Error("Live smoke requires HTTPS.");
const output = resolve(process.env.SMOKE_OUTPUT ?? "../../artifacts/live-integrity-report");
await mkdir(output, { recursive: true });
const browser = await chromium.launch({ executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH });
const context = await browser.newContext({ viewport: { width: 1280, height: 800 } });
try {
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", error => errors.push(error.message));
  page.on("console", message => { if (message.type() === "error") errors.push(message.text()); });
  await page.goto(`${origin}/login`);
  await page.getByLabel("Tên đăng nhập", { exact: true }).fill(process.env.SMOKE_USERNAME);
  await page.getByLabel("Mật khẩu", { exact: true }).fill(process.env.SMOKE_PASSWORD);
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL("**/issue");

  const stream = "BT /F1 18 Tf 72 720 Td (SplitBind synthetic integrity smoke) Tj ET";
  const objects = [
    "<< /Type /Catalog /Pages 2 0 R >>",
    "<< /Type /Pages /Kids [3 0 R] /Count 1 >>",
    "<< /Type /Page /Parent 2 0 R /MediaBox [0 0 612 792] /Resources << /Font << /F1 4 0 R >> >> /Contents 5 0 R >>",
    "<< /Type /Font /Subtype /Type1 /BaseFont /Helvetica >>",
    `<< /Length ${Buffer.byteLength(stream)} >>\nstream\n${stream}\nendstream`,
  ];
  let pdf = "%PDF-1.4\n";
  const offsets = objects.map((object, index) => {
    const offset = Buffer.byteLength(pdf);
    pdf += `${index + 1} 0 obj\n${object}\nendobj\n`;
    return offset;
  });
  const xref = Buffer.byteLength(pdf);
  pdf += `xref\n0 6\n0000000000 65535 f \n${offsets.map(offset => `${String(offset).padStart(10, "0")} 00000 n \n`).join("")}trailer\n<< /Size 6 /Root 1 0 R >>\nstartxref\n${xref}\n%%EOF\n`;
  await page.getByLabel("Tệp PDF", { exact: true }).setInputFiles({ name: "synthetic-smoke.pdf", mimeType: "application/pdf", buffer: Buffer.from(pdf) });
  await page.getByLabel("Mã người nhận", { exact: true }).fill(process.env.SMOKE_RECIPIENT_ID);
  const issuanceResponse = page.waitForResponse(response => response.url() === `${origin}/api/v1/issuances` && response.request().method() === "POST");
  await page.getByRole("button", { name: "Tạo bản cấp phát", exact: true }).click();
  const created = await issuanceResponse;
  expect(created.status()).toBe(201);
  const issuance = await created.json();
  await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
  await page.getByRole("link", { name: "Mở hồ sơ cấp phát" }).click();
  await expect(page.getByRole("heading", { name: "Bản cấp phát đã sẵn sàng" })).toBeVisible();
  await page.screenshot({ path: `${output}/issued.png`, fullPage: true });
  let download;
  await page.route(`**/issuances/${issuance.id}/result`, async route => {
    const response = await route.fetch();
    download = await response.json();
    await route.fulfill({ response });
  });
  const resultResponse = page.waitForResponse(response => response.url().endsWith(`/issuances/${issuance.id}/result`));
  await page.getByRole("button", { name: "Tải PDF kết quả", exact: true }).click();
  expect((await resultResponse).status()).toBe(200);
  const artifact = await context.request.get(download.download_url);
  expect(artifact.status()).toBe(200);
  const issued = await artifact.body();

  for (const modified of [false, true]) {
    await page.goto(`${origin}/verify`);
    await page.getByLabel("Tệp cần kiểm chứng", { exact: true }).setInputFiles({
      name: modified ? "modified-smoke.pdf" : "intact-smoke.pdf", mimeType: "application/pdf",
      buffer: modified ? Buffer.concat([issued, Buffer.from("\n% synthetic byte change\n")]) : issued,
    });
    const verificationResponse = page.waitForResponse(response => response.url() === `${origin}/api/v1/verifications` && response.request().method() === "POST");
    await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
    const createdVerification = await verificationResponse;
    expect(createdVerification.status()).toBe(201);
    const verification = await createdVerification.json();
    await expect(page.getByRole("heading", { name: "Hoàn tất", exact: true })).toBeVisible({ timeout: 120000 });
    await page.getByRole("link", { name: "Mở hồ sơ kiểm chứng" }).click();
    for (const [width, height] of [[1920, 1080], [1280, 800], [768, 1024], [375, 667]]) {
      await page.setViewportSize({ width, height });
      await page.emulateMedia({ reducedMotion: width === 375 ? "reduce" : "no-preference" });
      await page.goto(`${origin}/verifications/${verification.id}`);
      await expect(page.getByRole("heading", { name: modified ? "Chưa tìm thấy bản cấp phát khớp" : "Tệp khớp bản cấp phát", exact: true })).toBeVisible();
      await page.locator("summary").focus();
      await page.keyboard.press("Enter");
      await expect(page.getByRole("heading", { name: "Bằng chứng đối chiếu" })).toBeVisible();
      await expect(page.locator("main")).not.toContainText(/API|Số phiếu|Điểm fingerprint|Điểm toàn vẹn|Vùng toàn vẹn nghi vấn/);
      if (modified) await expect(page.getByText("Chưa kiểm tra — chưa tìm được bản cấp phát")).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.evaluate(() => window.scrollTo(0, 0));
      await page.screenshot({ path: `${output}/${modified ? "unmatched" : "intact"}-${width}.png`, fullPage: true });
    }
    const response = await context.request.get(`${origin}/api/v1/verifications/${verification.id}`);
    expect(response.status()).toBe(200);
    const result = await response.json();
    expect(result.evidence.algorithm_label).toBe("integrity_release_v1");
    expect(result.evidence.exact_file_hash_match).toBe(!modified);
    expect(result.evidence.manifest_signature_valid).toBe(modified ? null : true);
    console.log(JSON.stringify({ case: modified ? "unmatched" : "intact", status: result.status }));
    await page.setViewportSize({ width: 1280, height: 800 });
  }
  await page.getByRole("button", { name: "Đăng xuất khỏi SplitBind" }).click();
  await expect(page.getByRole("heading", { name: "Đăng nhập SplitBind" })).toBeVisible();
  expect(errors).toEqual([]);
  console.log("LIVE_INTEGRITY_SMOKE_PASSED");
} finally {
  await context.close();
  await browser.close();
}
