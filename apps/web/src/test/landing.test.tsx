import "@testing-library/jest-dom/vitest";

import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { appRoutes } from "../app/router";
import { createQueryClient } from "../app/queryClient";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const USER_ID = "00000000-0000-4000-8000-000000000001";

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function renderApp(path: string) {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
  vi.unstubAllGlobals();
});

describe("SplitBind landing page", () => {
  it("greets an unauthenticated visitor instead of redirecting to the login form", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/");

    expect(await screen.findByRole("banner", { name: "Giới thiệu SplitBind" })).toBeVisible();
    expect(screen.queryByRole("form", { name: "Đăng nhập SplitBind" })).not.toBeInTheDocument();
  });

  it("sends an authenticated issuer to the workbench", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const url = String(input);
      if (url.includes("/api/v1/demo/capabilities")) return json({ enabled: false });
      return json({
        authenticated: true,
        csrf_token: "csrf-token",
        user: {
          id: USER_ID,
          username: "issuer.demo",
          role: "issuer",
          organization_id: ORGANIZATION_ID,
        },
      });
    }));

    renderApp("/");

    expect(await screen.findByRole("heading", { name: "Tạo bản cấp phát" })).toBeVisible();
  });

  it("keeps the landing reachable for a signed-in reader", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: true,
      csrf_token: "csrf-token",
      user: {
        id: USER_ID,
        username: "issuer.demo",
        role: "issuer",
        organization_id: ORGANIZATION_ID,
      },
    })));

    renderApp("/gioi-thieu");

    expect(await screen.findByRole("banner", { name: "Giới thiệu SplitBind" })).toBeVisible();
  });

  it("renders seven sections under one page heading", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/");

    await screen.findByRole("banner", { name: "Giới thiệu SplitBind" });
    expect(document.querySelectorAll("[data-landing-section]")).toHaveLength(7);
    expect(
      Array.from(document.querySelectorAll<HTMLElement>("[data-landing-section]"))
        .map((section) => section.dataset.landingSection),
    ).toEqual(["01", "02", "03", "04", "05", "06", "07"]);
    expect(screen.getAllByRole("heading", { level: 1 })).toHaveLength(1);
  });

  it("states the evidence boundary and never claims transformed-file detection", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/");

    const boundary = await screen.findByRole("region", { name: "Biên giới bằng chứng" });
    expect(boundary).toHaveTextContent("không phải bằng chứng");
    expect(boundary).toHaveTextContent("chưa khả dụng");
    const claimSections = Array.from(
      document.querySelectorAll<HTMLElement>("[data-landing-section]"),
    ).filter((section) => section.dataset.landingSection !== "05");
    expect(claimSections).toHaveLength(6);
    for (const section of claimSections) {
      expect(section.textContent ?? "").not.toMatch(/sau (khi )?biến đổi/i);
    }
  });

  it("issues no API request while rendering", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/gioi-thieu");

    await screen.findByRole("banner", { name: "Giới thiệu SplitBind" });
    expect(fetchMock.mock.calls.filter(([input]) => String(input).includes("/api/v1"))).toHaveLength(0);
  });

  it("leaves every section fully visible when reduced motion is requested", async () => {
    vi.stubGlobal("matchMedia", vi.fn().mockImplementation((query: string) => ({
      matches: query.includes("prefers-reduced-motion: reduce"),
      media: query,
      onchange: null,
      addListener: vi.fn(),
      removeListener: vi.fn(),
      addEventListener: vi.fn(),
      removeEventListener: vi.fn(),
      dispatchEvent: vi.fn(),
    })));
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/");

    await screen.findByRole("banner", { name: "Giới thiệu SplitBind" });
    const sections = Array.from(document.querySelectorAll<HTMLElement>("[data-landing-section]"));
    expect(sections).toHaveLength(7);
    for (const section of sections) {
      expect(section.style.opacity).toBe("");
    }
  });

  it("never lowers the opacity of the evidence boundary section", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/");

    await screen.findByRole("banner", { name: "Giới thiệu SplitBind" });
    const boundary = document.querySelector<HTMLElement>('[data-landing-section="05"]');
    expect(boundary).not.toBeNull();
    expect(boundary?.style.opacity).not.toBe("0");
  });
});
