import { expect, test, type Page } from "@playwright/test";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const VERIFICATION_ID = "00000000-0000-4000-8000-000000000007";

async function sessionAs(page: Page, role: "administrator" | "issuer" | "verifier" | "auditor") {
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ authenticated: true, csrf_token: "csrf-token", user: {
      id: USER_ID, username: `${role}.demo`, role, organization_id: ORGANIZATION_ID,
    } }),
  }));
}

test("authorization prevents an issuer from creating or reading verification records", async ({ page }) => {
  const verificationRequests: string[] = [];
  await sessionAs(page, "issuer");
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/verifications")) verificationRequests.push(path);
  });
  await page.goto("/verify");
  await expect(page.getByRole("heading", { name: "Không có quyền tạo kiểm chứng" })).toBeVisible();
  await expect(page.getByLabel("Tệp cần kiểm chứng")).toHaveCount(0);
  await page.goto(`/verifications/${VERIFICATION_ID}`);
  await expect(page.getByRole("heading", { name: "Không có quyền xem kiểm chứng" })).toBeVisible();
  expect(verificationRequests).toEqual([]);
});

test("authorization presents a foreign verification as a safe not-found denial", async ({ page }) => {
  await sessionAs(page, "auditor");
  await page.route(`**/api/v1/verifications/${VERIFICATION_ID}`, (route) => route.fulfill({
    status: 404, contentType: "application/json", body: JSON.stringify({ detail: "Private foreign record." }),
  }));
  await page.goto(`/verifications/${VERIFICATION_ID}`);
  await expect(page.getByRole("alert")).toContainText("Không tìm thấy dữ liệu trong phạm vi được cấp quyền", { timeout: 5_000 });
  await expect(page.getByText("Private foreign record.")).toHaveCount(0);
});

for (const role of ["administrator", "auditor", "verifier"] as const) {
  test(`authorization allows scoped ${role} verification detail`, async ({ page }) => {
    await sessionAs(page, role);
    await page.route(`**/api/v1/verifications/${VERIFICATION_ID}`, (route) => route.fulfill({
      contentType: "application/json",
      body: JSON.stringify({
        id: VERIFICATION_ID, job_id: null, job_status: null, status: "NO_WATERMARK",
        created_at: "2026-08-30T12:01:00Z", completed_at: "2026-08-30T12:03:00Z",
        evidence: { limitations: ["no_watermark_not_exclusion"] }, metrics: {},
      }),
    }));
    await page.goto(`/verifications/${VERIFICATION_ID}`);
    await expect(page.getByRole("heading", { name: "Không phát hiện watermark" })).toBeVisible();
    await expect(page.getByText("không có nghĩa tài liệu chắc chắn không thuộc hệ thống", { exact: false })).toBeVisible();
  });
}
