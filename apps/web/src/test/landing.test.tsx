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
});
