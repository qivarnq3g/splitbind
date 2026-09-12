import "@testing-library/jest-dom/vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import { DocumentFileInput } from "../components/DocumentFileInput";
import { createMemoryRouter, RouterProvider } from "react-router-dom";
import { afterEach, expect, it, vi } from "vitest";
import { appRoutes } from "../app/router";
import { createQueryClient } from "../app/queryClient";
import { verificationCopy } from "../features/evidence/copy";

afterEach(() => {
  cleanup();
  vi.unstubAllGlobals();
});
it("blocks login submission until session initialization has completed", async () => {
  let resolveSession!: (response: Response) => void;
  const pendingSession = new Promise<Response>((resolve) => { resolveSession = resolve; });
  const fetchRequest = vi.fn(() => pendingSession);
  vi.stubGlobal("fetch", fetchRequest);
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/login"] })} />
    </QueryClientProvider>,
  );
  const submit = screen.getByRole("button", { name: "Đăng nhập" });
  expect(submit).toBeDisabled();
  await waitFor(() => expect(fetchRequest).toHaveBeenCalledTimes(1));
  fireEvent.submit(screen.getByRole("form", { name: "Đăng nhập SplitBind" }));
  await act(async () => {});
  expect(fetchRequest).toHaveBeenCalledTimes(1);
  await act(async () => resolveSession(new Response(JSON.stringify({ authenticated: false, user: null }), {
    headers: { "Content-Type": "application/json" },
  })));
  await waitFor(() => expect(submit).toBeEnabled());
});
it("keeps login blocked after session failure and allows connection retry", async () => {
  const fetchRequest = vi.fn()
    .mockResolvedValueOnce(new Response("{}", { status: 503, headers: { "Content-Type": "application/json" } }))
    .mockResolvedValueOnce(new Response(JSON.stringify({ authenticated: false, user: null }), { headers: { "Content-Type": "application/json" } }));
  vi.stubGlobal("fetch", fetchRequest);
  const client = createQueryClient();
  client.setDefaultOptions({ queries: { retry: false } });
  render(<QueryClientProvider client={client}><RouterProvider router={createMemoryRouter(appRoutes, { initialEntries: ["/login"] })} /></QueryClientProvider>);
  await screen.findByRole("alert");
  expect(screen.getByRole("button", { name: "Đăng nhập" })).toBeDisabled();
  fireEvent.click(screen.getByRole("button", { name: "Thử lại kết nối" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Đăng nhập" })).toBeEnabled());
});
it("sends an authenticated verifier to verification instead of the forbidden issuance page", async () => {
  vi.stubGlobal(
    "fetch",
    async () =>
      new Response(
        JSON.stringify({
          authenticated: true,
          user: { username: "review", role: "verifier" },
        }),
        { headers: { "Content-Type": "application/json" } },
      ),
  );
  const router = createMemoryRouter(appRoutes, { initialEntries: ["/login"] });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
  await screen.findByRole("heading", { name: "Xác minh tài liệu" }, { timeout: 5000 });
  expect(router.state.location.pathname).toBe("/verify");
});
it.each(["PROCESSING_FAILED", "INVALID_MANIFEST"] as const)(
  "does not conceal %s behind a file mismatch",
  (status) => {
    const copy = verificationCopy(status, "integrity_release_v1", false);
    expect(copy.label).toBe(
      status === "PROCESSING_FAILED"
        ? "Xử lý thất bại"
        : "Hồ sơ cấp phát không hợp lệ",
    );
  },
);
it("allows a dropped file to satisfy the form and provides a remove action", () => {
  const change = vi.fn();
  const { rerender } = render(
    <DocumentFileInput
      id="file"
      label="Document"
      accept=".pdf"
      describedBy="help"
      disabled={false}
      invalid={false}
      filename={null}
      onChange={change}
    />,
  );
  const file = new File(["pdf"], "document.pdf", { type: "application/pdf" });
  fireEvent.drop(document.querySelector(".file-picker")!, {
    dataTransfer: { files: [file] },
  });
  expect(change).toHaveBeenCalledWith(file);
  rerender(
    <DocumentFileInput
      id="file"
      label="Document"
      accept=".pdf"
      describedBy="help"
      disabled={false}
      invalid={false}
      filename={file.name}
      onChange={change}
    />,
  );
  expect(screen.getByLabelText("Document")).not.toBeRequired();
  fireEvent.click(screen.getByRole("button", { name: "Bỏ tệp đã chọn" }));
  expect(change).toHaveBeenLastCalledWith(undefined);
});
it.each([
  "PARTIAL_EVIDENCE",
  "PROCESSING_FAILED",
  "INVALID_MANIFEST",
  "NO_WATERMARK",
])("does not accuse tampering for %s", async (status) => {
  vi.stubGlobal("fetch", async (input: Request) => {
    const path = new URL(input.url).pathname;
    const data = path.endsWith("/session")
      ? { authenticated: true, user: { username: "review", role: "verifier" } }
      : path.includes("/verifications/")
        ? {
            id: "record",
            status,
            job_status: "succeeded",
            created_at: "2026-09-08T00:00:00Z",
            evidence: {
              manifest_signature_valid: null,
              exact_file_hash_match: null,
            },
          }
        : { enabled: false };
    return new Response(JSON.stringify(data), {
      headers: { "Content-Type": "application/json" },
    });
  });
  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider
        router={createMemoryRouter(appRoutes, {
          initialEntries: ["/verifications/record"],
        })}
      />
    </QueryClientProvider>,
  );
  await screen.findByText("record");
  expect(document.body).not.toHaveTextContent(
    "Tài liệu đã bị can thiệp hoặc giả mạo",
  );
  expect(document.body).not.toHaveTextContent("Đã đối soát");
});

it("displays dynamic ETA for pending job and total duration for completed job on JobDetailPage", async () => {
  vi.stubGlobal("fetch", async (input: Request) => {
    const path = new URL(input.url).pathname;
    if (path.endsWith("/session")) {
      return new Response(JSON.stringify({
        authenticated: true,
        user: { username: "review", role: "verifier" },
      }), { headers: { "Content-Type": "application/json" } });
    }
    if (path === "/api/v1/jobs/job-pending") {
      return new Response(JSON.stringify({
        id: "00000000-0000-4000-8000-000000000005",
        kind: "issuance",
        status: "processing",
        attempt: 0,
        issuance_id: null,
        created_at: new Date().toISOString(),
        updated_at: new Date().toISOString(),
        deadline_at: new Date(Date.now() + 600000).toISOString(),
        cancel_requested_at: null,
        safe_error_code: null,
      }), { headers: { "Content-Type": "application/json" } });
    }
    if (path === "/api/v1/jobs/job-done") {
      return new Response(JSON.stringify({
        id: "00000000-0000-4000-8000-000000000006",
        kind: "verification",
        status: "succeeded",
        attempt: 0,
        verification_id: "00000000-0000-4000-8000-000000000007",
        created_at: "2026-09-08T10:00:00Z",
        updated_at: "2026-09-08T10:00:08Z",
        deadline_at: "2026-09-08T10:10:00Z",
        cancel_requested_at: null,
        safe_error_code: null,
      }), { headers: { "Content-Type": "application/json" } });
    }
    return new Response(JSON.stringify({ enabled: false }), { headers: { "Content-Type": "application/json" } });
  });

  const { unmount } = render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider
        router={createMemoryRouter(appRoutes, {
          initialEntries: ["/jobs/job-pending"],
        })}
      />
    </QueryClientProvider>,
  );

  // design.md forbids inventing a time remaining, so the waiting note may report
  // only elapsed time measured from the server timestamps.
  expect(await screen.findByText(/Đã xử lý: \d+s/)).toBeVisible();
  expect(screen.queryByText(/ước tính/i)).toBeNull();
  unmount();

  render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider
        router={createMemoryRouter(appRoutes, {
          initialEntries: ["/jobs/job-done"],
        })}
      />
    </QueryClientProvider>,
  );

  expect(await screen.findByText(/Đã hoàn tất sau 8 giây/)).toBeVisible();
});
