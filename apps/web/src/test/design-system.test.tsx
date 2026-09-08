import "@testing-library/jest-dom/vitest";

import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, describe, expect, it, vi } from "vitest";

import { appRoutes } from "../app/router";
import { createQueryClient } from "../app/queryClient";
import { CryptographicMotif } from "../components/CryptographicMotif";

const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const USER_ID = "00000000-0000-4000-8000-000000000001";
const JOB_ID = "00000000-0000-4000-8000-000000000006";
const VERIFICATION_ID = "00000000-0000-4000-8000-000000000007";

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

describe("SplitBind design system", () => {
  it("uses only declared design tokens", () => {
    const tokens = readFileSync(resolve(process.cwd(), "tokens.css"), "utf8");
    const styles = readFileSync(resolve(process.cwd(), "src/styles/app.css"), "utf8");
    const source = `${tokens}\n${styles}`;
    const definitions = new Set(Array.from(source.matchAll(/(--[a-z0-9-]+)\s*:/g), (match) => match[1]));
    const references = new Set(Array.from(source.matchAll(/var\((--[a-z0-9-]+)/g), (match) => match[1]));

    expect([...references].filter((token) => !definitions.has(token))).toEqual([]);
  });

  it("keeps compact controls keyboard-sized and removes active motion when requested", () => {
    const styles = readFileSync(resolve(process.cwd(), "src/styles/app.css"), "utf8");

    expect(styles).toMatch(/\.copy-identifier\s*\{[^}]*min-width:\s*var\(--control-height\)[^}]*min-height:\s*var\(--control-height\)/s);
    expect(styles).toMatch(/\.technical-details summary\s*\{[^}]*min-height:\s*var\(--control-height\)/s);
    expect(styles).toMatch(/@media \(prefers-reduced-motion: reduce\)\s*\{[\s\S]*\.copy-identifier:active[\s\S]*transform:\s*none/s);
  });

  it("separates product context from the secure login form", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json({
      authenticated: false,
      csrf_token: "csrf-token",
      user: null,
    })));

    renderApp("/login");

    const introduction = await screen.findByRole("complementary", { name: "Giới thiệu SplitBind" });
    expect(introduction).toBeVisible();
    expect(screen.getByText("Bảo vệ tài liệu quan trọng")).toBeVisible();
    expect(screen.getAllByRole("heading")).toHaveLength(1);
    expect(introduction).toHaveTextContent("Cấp phát và kiểm tra tài liệu trong một nơi.");
    expect(introduction.querySelectorAll("p, h2, dl")).toHaveLength(2);
    expect(screen.getByRole("form", { name: "Đăng nhập SplitBind" })).toBeVisible();
    expect(screen.queryByText(/localStorage/i)).not.toBeInTheDocument();
    expect(document.querySelector("[data-motion-page]")).toBeInTheDocument();
  });

  it("uses one compact app header and a deliberate upload surface", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") {
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
      }
      if (path === "/api/v1/demo/capabilities") {
        return json({
          enabled: false,
          processing_limits: {
            max_pdf_pages: 5,
            max_pdf_bytes: 10 * 1024 * 1024,
            max_image_pixels: 40_000_000,
          },
          algorithm_label: "experimental_unreleased_fingerprint_v2",
        });
      }
      return json({ detail: "Not found." }, 404);
    }));

    renderApp("/issue");

    expect(await screen.findByText("Chọn PDF và người nhận để tạo bản cấp phát riêng.")).toBeVisible();
    expect(document.querySelector(".app-shell")).toBeVisible();
    expect(await screen.findByRole("banner", { name: "Thanh ứng dụng SplitBind" })).toBeVisible();
    expect(await screen.findByRole("navigation", { name: "Điều hướng chính" })).toBeVisible();
    expect(await screen.findByText("issuer.demo")).toBeVisible();
    expect(document.querySelector(".upload-dropzone input[type='file']")).toBeInTheDocument();
    expect(screen.getByRole("status", { name: "Tiến độ tải tệp" })).toBeVisible();
    expect(screen.getByText("Chọn tệp")).toBeVisible();
    expect(screen.getByText("Chưa chọn tệp")).toBeVisible();
    expect(document.body).not.toHaveTextContent(/API|endpoint|worker|UUID/i);
    expect(document.querySelector("[data-motion-page]")).toBeInTheDocument();
  });

  it("shows a short demo warning instead of a two-column technical banner", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") {
        return json({
          authenticated: true,
          csrf_token: "csrf-token",
          user: { id: USER_ID, username: "issuer.demo", role: "issuer", organization_id: ORGANIZATION_ID },
        });
      }
      return json({
        enabled: true,
        processing_limits: { max_pdf_pages: 5, max_pdf_bytes: 10 * 1024 * 1024, max_image_pixels: 40_000_000 },
        algorithm_label: "experimental_unreleased_fingerprint_v2",
      });
    }));

    renderApp("/issue");

    const banner = await screen.findByRole("complementary", { name: "Giới hạn chế độ demo" });
    expect(banner.querySelectorAll("p")).toHaveLength(1);
    expect(banner).toHaveTextContent("Bản demo. Kết quả chỉ mang tính kỹ thuật, không xác định người làm rò rỉ hoặc chỉnh sửa.");
  });

  it("describes the production integrity capability without calling it a demo", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") {
        return json({
          authenticated: true,
          csrf_token: "csrf-token",
          user: { id: USER_ID, username: "issuer.demo", role: "issuer", organization_id: ORGANIZATION_ID },
        });
      }
      return json({
        enabled: true,
        processing_limits: { max_pdf_pages: 5, max_pdf_bytes: 10 * 1024 * 1024, max_image_pixels: 40_000_000 },
        algorithm_label: "integrity_release_v1",
        hidden_fingerprint_enabled: false,
        transformed_attribution_available: false,
      });
    }));

    renderApp("/issue");

    const banner = await screen.findByRole("complementary", { name: "Khả năng xác minh" });
    expect(banner).toHaveTextContent("Xác minh chính xác file đã cấp phát");
    expect(banner).toHaveTextContent("Nhận diện fingerprint sau biến đổi chưa khả dụng");
    expect(banner).not.toHaveTextContent("Bản demo");
  });

  it("shortens long identifiers and copies the full value on demand", async () => {
    const writeText = vi.fn().mockResolvedValue(undefined);
    Object.defineProperty(navigator, "clipboard", { configurable: true, value: { writeText } });
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") {
        return json({
          authenticated: true,
          csrf_token: "csrf-token",
          user: { id: USER_ID, username: "administrator.demo", role: "administrator", organization_id: ORGANIZATION_ID },
        });
      }
      if (path === `/api/v1/jobs/${JOB_ID}`) {
        return json({
          id: JOB_ID,
          kind: "verification",
          status: "succeeded",
          attempt: 0,
          issuance_id: null,
          verification_id: VERIFICATION_ID,
          deadline_at: "2026-08-30T12:11:00Z",
          cancel_requested_at: null,
          safe_error_code: null,
          created_at: "2026-08-30T12:01:00Z",
          updated_at: "2026-08-30T12:03:00Z",
        });
      }
      return json({ enabled: false, processing_limits: {}, algorithm_label: null });
    }));

    renderApp(`/jobs/${JOB_ID}`);

    expect(await screen.findByText("00000000…0006")).toBeVisible();
    expect(screen.getByRole("status", { name: "Trạng thái công việc: Hoàn tất" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Sao chép mã công việc" }));
    await waitFor(() => expect(screen.getByRole("button", { name: "Đã sao chép mã công việc" })).toBeVisible());
    expect(writeText).toHaveBeenCalledWith(JOB_ID);
  });

  it("renders CryptographicMotif with semantic SVG and updates visual elements by stage", () => {
    const { rerender } = render(<CryptographicMotif stage="idle" size={200} />);

    const motif = screen.getByRole("img", { name: /cryptographic motif/i });
    expect(motif).toBeInTheDocument();
    expect(motif.tagName.toLowerCase()).toBe("svg");
    expect(motif.closest(".cryptographic-motif")).toHaveAttribute("data-stage", "idle");

    expect(motif.querySelector(".motif-backdrop")).toBeInTheDocument();
    expect(motif.querySelector(".motif-axes")).toBeInTheDocument();
    expect(motif.querySelector(".motif-wavelets")).toBeInTheDocument();
    expect(motif.querySelector(".motif-hash-fragments")).toBeInTheDocument();
    expect(motif.querySelectorAll(".motif-node").length).toBeGreaterThanOrEqual(4);
    expect(motif.querySelector(".motif-seal")).toBeInTheDocument();

    rerender(<CryptographicMotif stage="decomposing" />);
    expect(motif.closest(".cryptographic-motif")).toHaveAttribute("data-stage", "decomposing");

    rerender(<CryptographicMotif stage="sealed" />);
    expect(motif.closest(".cryptographic-motif")).toHaveAttribute("data-stage", "sealed");

    rerender(<CryptographicMotif stage="tampered" />);
    expect(motif.closest(".cryptographic-motif")).toHaveAttribute("data-stage", "tampered");
  });
});
