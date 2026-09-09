import { expect, test, type Page, type Route } from "@playwright/test";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const RECIPIENT_ID = "00000000-0000-4000-8000-000000000003";
const UPLOAD_ID = "00000000-0000-4000-8000-000000000004";
const ISSUANCE_ID = "00000000-0000-4000-8000-000000000005";
const JOB_ID = "00000000-0000-4000-8000-000000000006";
const PDF_SHA256 = "4f1949e95440af0ece666ebd5f399c1d77d22de639950784d349fa5feb47dca5";

function body(data: unknown): string {
  return JSON.stringify(data);
}

async function fulfillApi(route: Route) {
  const url = new URL(route.request().url());
  const response = (data: unknown, status = 200) => route.fulfill({
    status,
    contentType: "application/json",
    body: body(data),
  });

  if (url.pathname === "/api/v1/auth/session") {
    return response({
      authenticated: true,
      csrf_token: "csrf-token",
      user: {
        id: USER_ID,
        username: "issuer.demo",
        role: "issuer",
        organization_id: ORGANIZATION_ID,
      },
    });
  }
  if (url.pathname === "/api/v1/uploads") {
    return response({
      id: UPLOAD_ID,
      object_key: "uploads/orphan/input.pdf",
      expected_sha256: PDF_SHA256,
      size_bytes: 14,
      expires_at: "2026-08-30T12:15:00Z",
      finalized_at: null,
      upload_url: "https://storage.example.test/direct-upload",
      required_headers: {
        "Content-Type": "application/pdf",
        "x-amz-meta-sha256": PDF_SHA256,
      },
    }, 201);
  }
  if (url.pathname === `/api/v1/uploads/${UPLOAD_ID}/complete`) {
    return response({
      id: UPLOAD_ID,
      object_key: "uploads/orphan/input.pdf",
      expected_sha256: PDF_SHA256,
      size_bytes: 14,
      expires_at: "2026-08-30T12:15:00Z",
      finalized_at: "2026-08-30T12:01:00Z",
    });
  }
  if (url.pathname === "/api/v1/issuances") {
    return response({
      id: ISSUANCE_ID,
      job_id: JOB_ID,
      status: "created",
      issued_at: "2026-08-30T12:01:00Z",
    }, 201);
  }
  if (url.pathname === `/api/v1/jobs/${JOB_ID}`) {
    return response({
      id: JOB_ID,
      kind: "issuance",
      status: "processing",
      attempt: 0,
      issuance_id: ISSUANCE_ID,
      verification_id: null,
      deadline_at: "2026-08-30T12:11:00Z",
      cancel_requested_at: null,
      safe_error_code: null,
      created_at: "2026-08-30T12:01:00Z",
      updated_at: "2026-08-30T12:02:00Z",
    });
  }
  return response({ detail: "Not found." }, 404);
}

async function mockIssuerContract(page: Page) {
  await page.context().addCookies([{ name: "csrftoken", value: "csrf-token", url: "http://127.0.0.1:4173" }]);
  await page.route("**/api/v1/**", fulfillApi);
}

test("issuance browser contract journey", async ({ page }) => {
  const workflow: string[] = [];
  await mockIssuerContract(page);
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (!["/api/v1/auth/session", "/api/v1/demo/capabilities"].includes(path) && (path.startsWith("/api/v1/") || path === "/direct-upload")) {
      workflow.push(path);
    }
  });
  await page.route("https://storage.example.test/direct-upload", async (route) => {
    expect(route.request().headers()["x-amz-meta-sha256"]).toBe(PDF_SHA256);
    expect(route.request().headers().cookie).toBeUndefined();
    await route.fulfill({ status: 200, body: "" });
  });

  await page.goto("/issue");
  await page.getByLabel("Tệp PDF").setInputFiles({
    name: "course.pdf",
    mimeType: "application/pdf",
    buffer: Buffer.from("%PDF-1.4\n%%EOF"),
  });
  await page.getByLabel("Mã người nhận").fill(RECIPIENT_ID);
  await page.getByRole("button", { name: "Tạo bản cấp phát" }).click();

  await expect(page.getByText("Đang xử lý")).toBeVisible();
  expect(workflow.slice(0, 5)).toEqual([
    "/api/v1/uploads",
    "/direct-upload",
    `/api/v1/uploads/${UPLOAD_ID}/complete`,
    "/api/v1/issuances",
    `/api/v1/jobs/${JOB_ID}`,
  ]);
});

test("issuance workbench does not overflow supported narrow widths", async ({ page }, testInfo) => {
  await mockIssuerContract(page);
  for (const width of [320, 375, 414, 768, 1024]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/issue");
    await expect(page.getByRole("heading", { name: "Tạo bản cấp phát" })).toBeVisible();
    const dimensions = await page.evaluate(() => ({
      viewport: document.documentElement.clientWidth,
      scroll: document.documentElement.scrollWidth,
    }));
    expect(dimensions.scroll, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(dimensions.viewport);
    const button = await page.getByRole("button", { name: "Tạo bản cấp phát" }).boundingBox();
    expect(button?.height, `button touch target at ${width}px`).toBeGreaterThanOrEqual(44);
    await page.screenshot({ path: testInfo.outputPath(`issuance-${width}.png`), fullPage: true });
  }
});
