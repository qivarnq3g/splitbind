import "@testing-library/jest-dom/vitest";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { describe, expect, it, vi } from "vitest";

import { appRoutes } from "../app/router";

function createQueryClient() {
  return new QueryClient({
    defaultOptions: {
      queries: { retry: false, gcTime: 0 },
    },
  });
}

const mockJobs = [
  {
    id: "11111111-1111-4000-8000-111111111111",
    kind: "issuance",
    status: "succeeded",
    attempt: 0,
    issuance_id: "22222222-2222-4000-8000-222222222222",
    verification_id: null,
    deadline_at: "2026-09-10T12:00:00Z",
    cancel_requested_at: null,
    safe_error_code: null,
    created_at: "2026-09-10T10:00:00Z",
    updated_at: "2026-09-10T10:00:10Z",
    recipient_email: "alice@example.com",
    recipient_name: "Alice Nguyen",
    verification_status: null,
  },
  {
    id: "33333333-3333-4000-8000-333333333333",
    kind: "verification",
    status: "succeeded",
    attempt: 0,
    issuance_id: null,
    verification_id: "44444444-4444-4000-8000-444444444444",
    deadline_at: "2026-09-10T12:00:00Z",
    cancel_requested_at: null,
    safe_error_code: null,
    created_at: "2026-09-10T11:00:00Z",
    updated_at: "2026-09-10T11:00:05Z",
    recipient_email: null,
    recipient_name: null,
    verification_status: "VERIFIED_INTACT",
  },
];

describe("HistoryPage", () => {
  it("renders history list with jobs, full IDs, and action links", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/v1/auth/session")) {
        return new Response(
          JSON.stringify({
            authenticated: true,
            user: { username: "operator", role: "administrator" },
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/jobs")) {
        return new Response(JSON.stringify(mockJobs), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ enabled: false }), {
        headers: { "Content-Type": "application/json" },
      });
    });

    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider
          router={createMemoryRouter(appRoutes, {
            initialEntries: ["/history"],
          })}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByRole("heading", { name: "Lịch sử xử lý" })).toBeVisible();
    expect(await screen.findByText("alice@example.com")).toBeVisible();
    expect(screen.getByText("(Alice Nguyen)")).toBeVisible();
    expect(screen.getByText("11111111-1111-4000-8000-111111111111")).toBeVisible();
    expect(screen.getByText("33333333-3333-4000-8000-333333333333")).toBeVisible();
    // The verdict is shown to operators as Vietnamese copy, never as the raw
    // API enum; the enum remains available to assistive tech via data-vstatus.
    expect(screen.getByText("Đã xác minh toàn vẹn")).toBeVisible();
    expect(screen.queryByText("VERIFIED_INTACT")).not.toBeInTheDocument();
    expect(screen.getByRole("link", { name: /Mở hồ sơ cấp phát/ })).toHaveAttribute(
      "href",
      "/issuances/22222222-2222-4000-8000-222222222222",
    );
    expect(screen.getByRole("link", { name: /Mở hồ sơ kiểm chứng/ })).toHaveAttribute(
      "href",
      "/verifications/44444444-4444-4000-8000-444444444444",
    );
  });

  it("shows empty state when no jobs exist", async () => {
    vi.stubGlobal("fetch", async (input: RequestInfo | URL) => {
      const url = typeof input === "string" ? input : input instanceof URL ? input.href : input.url;
      if (url.includes("/api/v1/auth/session")) {
        return new Response(
          JSON.stringify({
            authenticated: true,
            user: { username: "operator", role: "issuer" },
          }),
          { headers: { "Content-Type": "application/json" } },
        );
      }
      if (url.includes("/api/v1/jobs")) {
        return new Response(JSON.stringify([]), {
          headers: { "Content-Type": "application/json" },
        });
      }
      return new Response(JSON.stringify({ enabled: false }), {
        headers: { "Content-Type": "application/json" },
      });
    });

    render(
      <QueryClientProvider client={createQueryClient()}>
        <RouterProvider
          router={createMemoryRouter(appRoutes, {
            initialEntries: ["/history"],
          })}
        />
      </QueryClientProvider>,
    );

    expect(await screen.findByText("Chưa có công việc nào")).toBeVisible();
  });
});
