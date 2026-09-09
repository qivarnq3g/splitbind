import { chromium, expect } from "@playwright/test";
import { mkdir } from "node:fs/promises";

const phase = process.argv[2] ?? "before";
const output = `../../artifacts/frontend-refinement/${phase}`;
await mkdir(output, { recursive: true });
const browser = await chromium.launch({
  executablePath: process.env.PLAYWRIGHT_CHROMIUM_EXECUTABLE_PATH,
  headless: true,
});
const id = "00000000-0000-4000-8000-000000000001";
const now = "2026-09-08T12:00:00Z";
const errors = [];
for (const [width, height] of [
  [1920, 1080],
  [1280, 800],
  [768, 1024],
  [375, 667],
  [320, 667],
  [414, 896],
]) {
  if (process.env.QA_WIDTH && width !== Number(process.env.QA_WIDTH)) continue;
  const context = await browser.newContext({ viewport: { width, height } });
  const page = await context.newPage();
  page.on("pageerror", (e) => errors.push(e.message));
  page.on("console", message => { if (message.type() === "error" && !message.text().includes("Failed to load resource")) errors.push(message.text()); });
  let authenticated = false;
  let kind = "issuance";
  let status = "processing";
  let verdict = "VERIFIED_INTACT";
  let uploadFailure = false;
  let loginFailure = false;
  const session = () => ({
    authenticated,
    csrf_token: "qa-only",
    user: authenticated
      ? {
          id,
          username: "review.operator",
          role: "administrator",
          organization_id: id,
        }
      : null,
  });
  await page.route("**/api/v1/**", async (route) => {
    const path = new URL(route.request().url()).pathname;
    let data;
    if (path.endsWith("/auth/session")) data = session();
    else if (path.endsWith("/auth/login")) {
      if (loginFailure) return route.fulfill({ status: 401, json: { detail: "Invalid credentials." } });
      authenticated = true;
      data = session();
    } else if (path.endsWith("/auth/logout")) {
      authenticated = false;
      data = session();
    } else if (path.endsWith("/demo/capabilities"))
      data = { enabled: false, algorithm_label: "integrity_release_v1" };
    else if (path === "/api/v1/uploads")
      data = {
        id,
        upload_url: "http://127.0.0.1:5173/qa-upload",
        required_headers: {},
        expected_sha256: "a".repeat(64),
      };
    else if (path.endsWith("/complete")) data = { id, finalized_at: now };
    else if (path === "/api/v1/issuances") {
      kind = "issuance";
      data = { id, job_id: id };
    } else if (path === "/api/v1/verifications") {
      kind = "verification";
      data = { id, job_id: id };
    } else if (path.includes("/jobs/"))
      data = {
        id,
        kind,
        status,
        attempt: 0,
        updated_at: now,
        created_at: now,
        issuance_id: kind === "issuance" ? id : null,
        verification_id: kind === "verification" ? id : null,
        safe_error_code: status === "failed" ? "INPUT_INVALID" : null,
      };
    else if (path.endsWith("/result")) data = { download_url: "http://127.0.0.1:5173/qa-result.pdf" };
    else if (path.includes("/issuances/"))
      data = {
        id,
        job_id: id,
        status: "succeeded",
        issued_at: now,
        result_available: true,
        algorithm_label: "integrity_release_v1",
      };
    else if (path.includes("/verifications/"))
      data = {
        id,
        job_id: id,
        job_status: "succeeded",
        created_at: now,
        status: verdict,
        evidence: {
          algorithm_label: "integrity_release_v1",
          exact_file_hash_match: verdict === "VERIFIED_INTACT",
          manifest_signature_valid: verdict === "VERIFIED_INTACT" ? true : null,
          suspicious_regions: null,
          limitations: [],
        },
      };
    else
      return route.fulfill({
        status: 404,
        json: { detail: "QA route not configured" },
      });
    await route.fulfill({ json: data });
  });
  await page.route("**/qa-upload", (route) =>
    route.fulfill({ status: uploadFailure ? 503 : 200, body: "" }),
  );
  await page.route("**/qa-result.pdf", route => route.fulfill({ contentType: "application/pdf", body: "%PDF-1.4\n%%EOF" }));
  const shot = async (name) => {
    await page.waitForTimeout(650);
    await page.evaluate(() => window.scrollTo(0, 0));
    if (await page.evaluate(() => document.documentElement.scrollWidth > innerWidth))
      throw new Error(`Horizontal overflow: ${name} at ${width}px`);
    await page.screenshot({
      path: `${output}/${name}-${width}.png`,
      fullPage: true,
    });
  };
  await page.goto("http://127.0.0.1:5173/login");
  await shot("login");
  await page
    .getByLabel("Tên đăng nhập", { exact: true })
    .fill("review.operator");
  await page.getByLabel("Mật khẩu", { exact: true }).fill("qa-fixture-only");
  await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
  await page.waitForURL("**/issue");
  await shot("issue");
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "Hop-dong-dich-vu.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n%%EOF"),
    });
  await page.getByLabel("Mã người nhận", { exact: true }).fill(id);
  await shot("issue-selected");
  await page
    .getByRole("button", { name: "Tạo bản cấp phát", exact: true })
    .click();
  await page.waitForURL("**/jobs/*");
  await shot("job");
  status = "succeeded";
  await page.reload();
  await shot("job-complete");
  await page.goto(`http://127.0.0.1:5173/issuances/${id}`);
  await shot("issued");
  if (width === 375) {
    const result = page.waitForEvent("download");
    await page.getByRole("button", { name: "Tải PDF kết quả", exact: true }).click();
    expect((await result).suggestedFilename()).toBe("splitbind-result.pdf");
  }
  await page.goto("http://127.0.0.1:5173/verify");
  await shot("verify");
  await page
    .locator("input[type=file]")
    .setInputFiles({
      name: "Ban-can-kiem-tra.pdf",
      mimeType: "application/pdf",
      buffer: Buffer.from("%PDF-1.4\n%%EOF"),
    });
  status = "processing";
  await page
    .getByRole("button", { name: "Bắt đầu xác minh", exact: true })
    .click();
  await page.waitForURL("**/jobs/*");
  await shot("verification-job");
  await page.goto(`http://127.0.0.1:5173/verifications/${id}`);
  await shot("intact");
  await page.getByText("Xem chi tiết kỹ thuật", { exact: true }).click();
  await shot("evidence");
  for (const result of [
    "SOURCE_IDENTIFIED_MODIFIED",
    "PARTIAL_EVIDENCE",
    "PROCESSING_FAILED",
  ]) {
    verdict = result;
    await page.reload();
    await shot(result.toLowerCase());
  }
  status = "failed";
  await page.goto(`http://127.0.0.1:5173/jobs/${id}`);
  await shot("failed");
  await page.emulateMedia({ reducedMotion: "reduce" });
  await page.goto("http://127.0.0.1:5173/verify");
  await shot("reduced-motion");
  expect(await page.locator(".route-stage").evaluate(element => getComputedStyle(element).opacity)).toBe("1");
  expect(await page.locator(".route-stage").evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === "running").length)).toBe(0);
  if (width === 375) {
    const picker = page.waitForEvent("filechooser");
    await page.locator("input[type=file]").click();
    await (await picker).setFiles({ name: `${"Tai-lieu-".repeat(18)}.pdf`, mimeType: "application/pdf", buffer: Buffer.from("%PDF-1.4\n%%EOF") });
    await shot("long-filename");
    uploadFailure = true;
    await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await expect(page.locator(".file-name")).toContainText("Tai-lieu-");
    await shot("upload-failure");
    uploadFailure = false;
    status = "processing";
    await page.getByRole("button", { name: "Bắt đầu xác minh", exact: true }).click();
    await page.waitForURL("**/jobs/*");
    await expect(page.getByRole("heading", { name: "Đang xử lý", exact: true })).toBeVisible();
    await page.waitForTimeout(6000);
    await shot("still-processing");
    await page.getByRole("link", { name: "Cấp phát", exact: true }).click();
    await page.getByRole("link", { name: "Xác minh", exact: true }).click();
    await expect(page.getByRole("heading", { name: "Xác minh tài liệu", exact: true })).toBeVisible();
    await page.getByRole("button", { name: "Đăng xuất khỏi SplitBind" }).click();
    await expect(page.getByRole("heading", { name: "Đăng nhập SplitBind" })).toBeVisible();
    await shot("logged-out");
    loginFailure = true;
    await page.getByLabel("Tên đăng nhập", { exact: true }).fill("review.operator");
    await page.getByLabel("Mật khẩu", { exact: true }).fill("qa-invalid-password");
    await page.getByRole("button", { name: "Đăng nhập", exact: true }).click();
    await expect(page.getByRole("alert")).toBeVisible();
    await shot("login-failure");
  }
  const contrast = await page.evaluate(() => {
    const style = getComputedStyle(document.documentElement);
    const canvas = document.createElement("canvas");
    canvas.width = canvas.height = 1;
    const context = canvas.getContext("2d");
    const luminance = name => {
      context.fillStyle = style.getPropertyValue(`--color-${name}`).trim();
      context.fillRect(0, 0, 1, 1);
      const rgb = [...context.getImageData(0, 0, 1, 1).data].slice(0, 3).map(value => {
        const channel = value / 255;
        return channel <= .04045 ? channel / 12.92 : ((channel + .055) / 1.055) ** 2.4;
      });
      return rgb[0] * .2126 + rgb[1] * .7152 + rgb[2] * .0722;
    };
    return [["ink", "paper"], ["muted", "paper"], ["muted", "surface"], ["accent-ink", "accent"], ["success", "paper"], ["error", "paper"], ["warning", "paper"], ["focus", "paper"]].map(([foreground, background]) => {
      const a = luminance(foreground), b = luminance(background);
      return { foreground, background, ratio: (Math.max(a, b) + .05) / (Math.min(a, b) + .05) };
    });
  });
  for (const pair of contrast) expect(pair.ratio, JSON.stringify(pair)).toBeGreaterThanOrEqual(pair.foreground === "focus" ? 3 : 4.5);
  console.log(
    JSON.stringify({
      width,
      overflow: await page.evaluate(
        () => document.documentElement.scrollWidth > innerWidth,
      ),
    }),
  );
  await context.close();
}
await browser.close();
console.log(JSON.stringify({ errors }));
if (errors.length) process.exitCode = 1;
