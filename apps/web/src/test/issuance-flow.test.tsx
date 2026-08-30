import "@testing-library/jest-dom/vitest";

import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appRoutes } from "../app/router";
import { createQueryClient } from "../app/queryClient";
import { jobPollingInterval } from "../features/jobs/useJob";
import { MAX_PDF_BYTES } from "../features/uploads/uploadIssuance";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const RECIPIENT_ID = "00000000-0000-4000-8000-000000000003";
const UPLOAD_ID = "00000000-0000-4000-8000-000000000004";
const ISSUANCE_ID = "00000000-0000-4000-8000-000000000005";
const JOB_ID = "00000000-0000-4000-8000-000000000006";
const PDF_SHA256 = "4f1949e95440af0ece666ebd5f399c1d77d22de639950784d349fa5feb47dca5";

type ObservedRequest = {
  path: string;
  method: string;
  credentials: RequestCredentials;
  headers: Headers;
  body: unknown;
};

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

function session(role: "issuer" | "auditor") {
  return {
    authenticated: true,
    csrf_token: "csrf-token",
    user: {
      id: USER_ID,
      username: role === "issuer" ? "issuer.demo" : "auditor.demo",
      role,
      organization_id: ORGANIZATION_ID,
    },
  };
}

function renderApp(path = "/issue") {
  const queryClient = createQueryClient();
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={queryClient}>
      <RouterProvider router={router} />
    </QueryClientProvider>,
  );
}

describe("issuance browser workflow", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=csrf-token";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("hashes, uploads, finalizes, creates, and follows an issuance job", async () => {
    const observed: ObservedRequest[] = [];
    let jobReads = 0;
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const request = input instanceof Request && init === undefined ? input : new Request(input, init);
      const url = new URL(request.url);
      const bodyText = request.method === "GET" || request.method === "HEAD" ? "" : await request.clone().text();
      const body = bodyText && request.headers.get("content-type")?.includes("application/json")
        ? JSON.parse(bodyText) as unknown
        : bodyText || null;
      observed.push({
        path: url.pathname,
        method: request.method,
        credentials: request.credentials,
        headers: new Headers(request.headers),
        body,
      });

      if (url.pathname === "/api/v1/auth/session") return json(session("issuer"));
      if (url.pathname === "/api/v1/uploads") {
        return json({
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
      if (url.hostname === "storage.example.test") return new Response(null, { status: 200 });
      if (url.pathname === `/api/v1/uploads/${UPLOAD_ID}/complete`) {
        return json({
          id: UPLOAD_ID,
          object_key: "uploads/orphan/input.pdf",
          expected_sha256: PDF_SHA256,
          size_bytes: 14,
          expires_at: "2026-08-30T12:15:00Z",
          finalized_at: "2026-08-30T12:01:00Z",
        });
      }
      if (url.pathname === "/api/v1/issuances") {
        return json({
          id: ISSUANCE_ID,
          job_id: JOB_ID,
          status: "created",
          issued_at: "2026-08-30T12:01:00Z",
        }, 201);
      }
      if (url.pathname === `/api/v1/jobs/${JOB_ID}`) {
        jobReads += 1;
        return json({
          id: JOB_ID,
          kind: "issuance",
          status: jobReads === 1 ? "processing" : "succeeded",
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
      return json({ detail: "Not found." }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    renderApp();
    const file = new File(["%PDF-1.4\n%%EOF"], "course.pdf", { type: "application/pdf" });
    fireEvent.change(await screen.findByLabelText("Tệp PDF"), { target: { files: [file] } });
    fireEvent.change(screen.getByLabelText("Mã người nhận"), { target: { value: RECIPIENT_ID } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    expect(await screen.findByText("Đang xử lý")).toBeVisible();

    const workflow = observed.filter((request) => request.path !== "/api/v1/auth/session");
    expect(workflow.map((request) => request.path)).toEqual([
      "/api/v1/uploads",
      "/direct-upload",
      `/api/v1/uploads/${UPLOAD_ID}/complete`,
      "/api/v1/issuances",
      `/api/v1/jobs/${JOB_ID}`,
    ]);
    expect(workflow[0]?.body).toEqual({
      kind: "issuance_input",
      filename: "course.pdf",
      content_type: "application/pdf",
      size_bytes: 14,
      sha256: PDF_SHA256,
    });
    expect(workflow[1]?.credentials).toBe("omit");
    expect(Object.fromEntries(workflow[1]!.headers.entries())).toMatchObject({
      "content-type": "application/pdf",
      "x-amz-meta-sha256": PDF_SHA256,
    });
    expect(workflow[2]?.body).toEqual({ sha256: PDF_SHA256 });
    expect(workflow[3]?.body).toEqual({
      recipient_id: RECIPIENT_ID,
      upload_id: UPLOAD_ID,
      correlation_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
    });
  });

  it("rejects a PDF above 10 MiB before requesting an upload intent", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      return new URL(request.url).pathname === "/api/v1/auth/session"
        ? json(session("issuer"))
        : json({ detail: "Unexpected request." }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    const oversized = new File([new Uint8Array(MAX_PDF_BYTES + 1)], "large.pdf", {
      type: "application/pdf",
    });
    fireEvent.change(await screen.findByLabelText("Tệp PDF"), { target: { files: [oversized] } });
    fireEvent.change(screen.getByLabelText("Mã người nhận"), { target: { value: RECIPIENT_ID } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Tệp vượt quá giới hạn 10 MiB");
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(1));
  });

  it("clears upload progress when the direct upload fails", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      if (url.pathname === "/api/v1/auth/session") return json(session("issuer"));
      if (url.pathname === "/api/v1/uploads") {
        return json({
          id: UPLOAD_ID,
          object_key: "uploads/orphan/input.pdf",
          expected_sha256: PDF_SHA256,
          size_bytes: 14,
          expires_at: "2026-08-30T12:15:00Z",
          finalized_at: null,
          upload_url: "https://storage.example.test/direct-upload",
          required_headers: { "Content-Type": "application/pdf" },
        }, 201);
      }
      if (url.hostname === "storage.example.test") return new Response(null, { status: 503 });
      return json({ detail: "Unexpected request." }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    fireEvent.change(await screen.findByLabelText("Tệp PDF"), {
      target: { files: [new File(["%PDF-1.4\n%%EOF"], "course.pdf", { type: "application/pdf" })] },
    });
    fireEvent.change(screen.getByLabelText("Mã người nhận"), { target: { value: RECIPIENT_ID } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tải tệp lên kho lưu trữ");
    expect(screen.queryByText("Đang tải tệp")).not.toBeInTheDocument();
  });

  it("locks the selected file and recipient while issuance is in progress", async () => {
    let releaseIntent!: (response: Response) => void;
    const pendingIntent = new Promise<Response>((resolve) => {
      releaseIntent = resolve;
    });
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const url = new URL(request.url);
      if (url.pathname === "/api/v1/auth/session") return json(session("issuer"));
      if (url.pathname === "/api/v1/uploads") return pendingIntent;
      if (url.hostname === "storage.example.test") return new Response(null, { status: 503 });
      return json({ detail: "Unexpected request." }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    const fileInput = await screen.findByLabelText("Tệp PDF");
    const recipientInput = screen.getByLabelText("Mã người nhận");
    fireEvent.change(fileInput, {
      target: { files: [new File(["%PDF-1.4\n%%EOF"], "course.pdf", { type: "application/pdf" })] },
    });
    fireEvent.change(recipientInput, { target: { value: RECIPIENT_ID } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    await waitFor(() => expect(fileInput).toBeDisabled());
    expect(recipientInput).toBeDisabled();

    releaseIntent(json({
      id: UPLOAD_ID,
      object_key: "uploads/orphan/input.pdf",
      expected_sha256: PDF_SHA256,
      size_bytes: 14,
      expires_at: "2026-08-30T12:15:00Z",
      finalized_at: null,
      upload_url: "https://storage.example.test/direct-upload",
      required_headers: { "Content-Type": "application/pdf" },
    }, 201));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tải tệp lên kho lưu trữ");
  });

  it("keeps the issuance screen read-only for an auditor", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json(session("auditor"))));
    renderApp();

    expect(await screen.findByText("Quyền chỉ đọc")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Tạo bản cấp phát" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Tệp PDF")).not.toBeInTheDocument();
  });
});

describe("job polling schedule", () => {
  it("backs off to five seconds and stops for every terminal state", () => {
    expect(jobPollingInterval("processing", 1, 0)).toBe(1_000);
    expect(jobPollingInterval("processing", 4, 0)).toBe(5_000);
    expect(jobPollingInterval("processing", 20, 0)).toBe(5_000);
    for (const status of ["succeeded", "failed", "dead_lettered", "cancelled"]) {
      expect(jobPollingInterval(status, 20, 20)).toBe(false);
    }
  });
});
