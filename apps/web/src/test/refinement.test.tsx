import "@testing-library/jest-dom/vitest";
import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, fireEvent } from "@testing-library/react";
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
        : "Manifest không hợp lệ",
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
