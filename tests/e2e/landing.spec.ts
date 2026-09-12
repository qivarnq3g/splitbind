import { expect, test, type Page } from "@playwright/test";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const USER_ID = "00000000-0000-4000-8000-000000000001";

async function anonymous(page: Page) {
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ authenticated: false, csrf_token: "csrf-token", user: null }),
  }));
}

async function signedIn(page: Page) {
  await page.route("**/api/v1/demo/capabilities", (route) => route.fulfill({ json: { enabled: false } }));
  await page.route("**/api/v1/auth/session", (route) => route.fulfill({
    contentType: "application/json",
    body: JSON.stringify({ authenticated: true, csrf_token: "csrf-token", user: {
      id: USER_ID, username: "issuer.demo", role: "issuer", organization_id: ORGANIZATION_ID,
    } }),
  }));
}

test("an anonymous visitor lands on the explanation, not the login form", async ({ page }) => {
  await anonymous(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { level: 1, name: "Tài liệu có nguồn. Niềm tin có cơ sở." })).toBeVisible();
  await expect(page.locator("[data-landing-section]")).toHaveCount(7);
});

test("the landing issues no API traffic of its own", async ({ page }) => {
  const apiPaths: string[] = [];
  await anonymous(page);
  page.on("request", (request) => {
    const path = new URL(request.url()).pathname;
    if (path.startsWith("/api/v1/") && !path.startsWith("/api/v1/auth/session")) apiPaths.push(path);
  });
  await page.goto("/gioi-thieu");
  await expect(page.getByRole("banner", { name: "Giới thiệu SplitBind" })).toBeVisible();
  expect(apiPaths).toEqual([]);
});

test("a signed-in issuer is forwarded to the workbench", async ({ page }) => {
  await signedIn(page);
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Tạo bản cấp phát" })).toBeVisible();
});

test("the landing never scrolls sideways", async ({ page }) => {
  await anonymous(page);
  for (const width of [1920, 1280, 768, 375]) {
    await page.setViewportSize({ width, height: 900 });
    await page.goto("/gioi-thieu");
    await expect(page.getByRole("banner", { name: "Giới thiệu SplitBind" })).toBeVisible();
    const overflow = await page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    expect(overflow, `horizontal overflow at ${width}px`).toBeLessThanOrEqual(0);
  }
});

test("reduced motion shows every section immediately", async ({ page }) => {
  await page.emulateMedia({ reducedMotion: "reduce" });
  await anonymous(page);
  await page.goto("/gioi-thieu");
  await expect(page.getByRole("region", { name: "Biên giới bằng chứng" })).toBeVisible();
  const hidden = await page.evaluate(() =>
    Array.from(document.querySelectorAll<HTMLElement>("[data-landing-section]"))
      .filter((section) => Number(getComputedStyle(section).opacity) < 0.99).length);
  expect(hidden).toBe(0);
});
