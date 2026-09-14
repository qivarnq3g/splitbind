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

    renderApp("/about");

    expect(await screen.findByRole("banner", { name: "Giới thiệu SplitBind" })).toBeVisible();
  });

  it("offers the workbench rather than a login prompt once signed in", async () => {
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

    renderApp("/about");

    await screen.findByRole("banner", { name: "Giới thiệu SplitBind" });
    const entries = await screen.findAllByRole("link", {
      name: "Vào không gian làm việc",
    });
    expect(entries.length).toBeGreaterThanOrEqual(2);
    for (const entry of entries) expect(entry).toHaveAttribute("href", "/issue");
    expect(screen.queryByRole("link", { name: "Đăng nhập" })).not.toBeInTheDocument();
  });

  it("still prompts an unauthenticated visitor to sign in", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/about");

    await screen.findByRole("banner", { name: "Giới thiệu SplitBind" });
    const prompts = screen.getAllByRole("link", { name: "Đăng nhập" });
    expect(prompts.length).toBeGreaterThanOrEqual(2);
    for (const prompt of prompts) expect(prompt).toHaveAttribute("href", "/login");
    expect(
      screen.queryByRole("link", { name: "Vào không gian làm việc" }),
    ).not.toBeInTheDocument();
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

  it("states what tracing can and cannot do, with the limits in the boundary section", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/");

    const boundary = await screen.findByRole("region", { name: "Biên giới bằng chứng" });
    expect(boundary).toHaveTextContent("không phải bằng chứng");
    expect(boundary).toHaveTextContent("cắt mất phần lớn nội dung");
    expect(boundary).toHaveTextContent("xoay nghiêng");
    expect(boundary).toHaveTextContent("chưa đạt ngưỡng");
    expect(boundary).toHaveTextContent("không bao giờ chứng minh được ai");
    const sections = Array.from(
      document.querySelectorAll<HTMLElement>("[data-landing-section]"),
    );
    expect(sections).toHaveLength(7);
    const claiming = sections.filter((section) =>
      /nén lại|thu nhỏ|chụp lại màn hình/i.test(section.textContent ?? ""),
    );
    expect(claiming.map((section) => section.dataset.landingSection).sort()).toEqual([
      "04",
      "05",
    ]);
  });

  it("issues no API request while rendering", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    }));
    vi.stubGlobal("fetch", fetchMock);

    renderApp("/about");

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

describe("root route while the session is still resolving", () => {
  it("never shows the landing page to a visitor who turns out to be signed in", async () => {
    let releaseSession: (() => void) | null = null;
    const held = new Promise<void>((resolve) => {
      releaseSession = resolve;
    });

    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url, "http://localhost");
      if (url.pathname === "/api/v1/auth/session") {
        await held;
        return json({
          authenticated: true,
          user: {
            id: USER_ID,
            username: "issuer",
            role: "issuer",
            organization: { id: ORGANIZATION_ID, name: "SplitBind", slug: "splitbind" },
          },
        });
      }
      return json({ detail: "Not found." }, 404);
    }));

    renderApp("/");

    // While the session is unknown the root route must hold, not guess.
    expect(await screen.findByRole("status", { name: "Đang kiểm tra phiên đăng nhập" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: /Tài liệu có nguồn/ })).toBeNull();

    releaseSession!();

    expect(await screen.findByRole("heading", { level: 1, name: "Tạo bản cấp phát" })).toBeVisible();
    expect(screen.queryByRole("heading", { level: 1, name: /Tài liệu có nguồn/ })).toBeNull();
  });
});
