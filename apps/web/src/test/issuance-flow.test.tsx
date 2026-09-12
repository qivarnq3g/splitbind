import "@testing-library/jest-dom/vitest";

import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  cache?: RequestCache;
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

function demoCapabilities(enabled: boolean) {
  return {
    enabled,
    processing_limits: {
      max_pdf_pages: 5,
      max_pdf_bytes: 10 * 1024 * 1024,
      max_image_pixels: 40_000_000,
    },
    algorithm_label: "experimental_unreleased_fingerprint_v2",
  };
}

function issuance(resultAvailable: boolean, status = "succeeded") {
  return {
    id: ISSUANCE_ID,
    job_id: JOB_ID,
    status,
    issued_at: "2026-08-30T12:01:00Z",
    result_available: resultAvailable,
    algorithm_label: resultAvailable ? "experimental_unreleased_fingerprint_v2" : null,
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
        cache: request.cache,
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
    fireEvent.change(screen.getByLabelText(/Email người nhận/i), { target: { value: "student@example.com" } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    expect(await screen.findByText("Đang xử lý")).toBeVisible();

    const workflow = observed.filter((request) => ![
      "/api/v1/auth/session",
      "/api/v1/demo/capabilities",
    ].includes(request.path));
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
      recipient_email: "student@example.com",
      upload_id: UPLOAD_ID,
      correlation_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
    });
  });

  it("rejects a PDF above the configured ceiling before requesting an upload intent", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      return new URL(request.url).pathname === "/api/v1/auth/session"
        ? json(session("issuer"))
        : json({ detail: "Unexpected request." }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    const oversized = new File([new Uint8Array(8)], "large.pdf", { type: "application/pdf" });
    Object.defineProperty(oversized, "size", { value: MAX_PDF_BYTES + 1 });
    fireEvent.change(await screen.findByLabelText("Tệp PDF"), { target: { files: [oversized] } });
    fireEvent.change(screen.getByLabelText(/Email người nhận/i), { target: { value: "student@example.com" } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    expect(await screen.findByRole("alert")).toHaveTextContent("Tệp vượt quá giới hạn 100 MB");
    expect(screen.getByRole("button", { name: "Tạo bản cấp phát" })).toBeDisabled();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
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
    fireEvent.change(screen.getByLabelText(/Email người nhận/i), { target: { value: "student@example.com" } });
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
    const recipientInput = screen.getByLabelText(/Email người nhận/i);
    fireEvent.change(fileInput, {
      target: { files: [new File(["%PDF-1.4\n%%EOF"], "course.pdf", { type: "application/pdf" })] },
    });
    fireEvent.change(recipientInput, { target: { value: "student@example.com" } });
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

  it("lets the issuer remove a local selection without starting a job", async () => {
    const requests: string[] = [];
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async input => {
      const request = input instanceof Request ? input : new Request(input);
      requests.push(request.method);
      return json(session("issuer"));
    }));
    renderApp();
    const fileInput = await screen.findByLabelText("Tệp PDF");
    fireEvent.change(fileInput, { target: { files: [new File(["%PDF-1.4"], "thesis.pdf", { type: "application/pdf" })] } });
    expect(screen.getByText("thesis.pdf")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Bỏ tệp đã chọn" }));
    expect(screen.queryByText("thesis.pdf")).not.toBeInTheDocument();
    expect(fileInput).toBeRequired();
    expect(requests).not.toContain("POST");
  });
  it("keeps the issuance screen read-only for an auditor", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json(session("auditor"))));
    renderApp();

    expect(await screen.findByText("Quyền chỉ đọc")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Tạo bản cấp phát" })).not.toBeInTheDocument();
    expect(screen.queryByLabelText("Tệp PDF")).not.toBeInTheDocument();
  });

  it("shows the local experimental demo banner only when enabled", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) return json(issuance(false, "processing"));
      return json({ detail: "Not found." }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);

    const view = renderApp(`/issuances/${ISSUANCE_ID}`);
    expect(await screen.findByText("Bản demo.")).toBeVisible();
    expect(screen.getByText(/Kết quả chỉ mang tính kỹ thuật, không xác định người làm rò rỉ hoặc chỉnh sửa/)).toBeVisible();

    view.unmount();
    cleanup();
    fetchMock.mockImplementation(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(false));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) return json(issuance(false, "processing"));
      return json({ detail: "Not found." }, 404);
    });
    renderApp(`/issuances/${ISSUANCE_ID}`);
    await screen.findByText("Kết quả PDF đang được xử lý.");
    expect(screen.queryByText("Chế độ demo cục bộ - vân tay thử nghiệm, chưa phát hành.")).not.toBeInTheDocument();
  });

  it("shows an honest processing state without a download action", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) return json(issuance(false, "processing"));
      return json({ detail: "Not found." }, 404);
    }));
    renderApp(`/issuances/${ISSUANCE_ID}`);

    expect(await screen.findByText("Kết quả PDF đang được xử lý.")).toBeVisible();
    expect(screen.queryByRole("button", { name: "Tải PDF kết quả" })).not.toBeInTheDocument();
  });

  it("labels and downloads an available experimental result using a fresh URL", async () => {
    const observed: string[] = [];
    const resultRequestCaches: RequestCache[] = [];
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      observed.push(path);
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) return json(issuance(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}/result`) {
        resultRequestCaches.push(request.cache);
        return json({
          download_url: "https://storage.example.test/signed-result.pdf",
          expires_at: "2026-08-30T12:06:00Z",
        });
      }
      return json({ detail: "Not found." }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    let downloadedHref = "";
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(function (this: HTMLAnchorElement) {
      downloadedHref = this.href;
    });
    renderApp(`/issuances/${ISSUANCE_ID}`);

    expect(await screen.findByText("Thử nghiệm - chưa phát hành")).toBeVisible();
    expect(observed).not.toContain(`/api/v1/issuances/${ISSUANCE_ID}/result`);
    fireEvent.click(screen.getByRole("button", { name: "Tải PDF kết quả" }));

    await waitFor(() => expect(downloadedHref).toBe("https://storage.example.test/signed-result.pdf"));
    expect(observed.filter((path) => path === `/api/v1/issuances/${ISSUANCE_ID}/result`)).toHaveLength(1);
    expect(screen.getByRole("button", { name: "Đã mở bản tải" })).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Đã mở bản tải" }));
    await waitFor(() => expect(observed.filter((path) => path === `/api/v1/issuances/${ISSUANCE_ID}/result`)).toHaveLength(2));
    expect(resultRequestCaches).toEqual(["no-store", "no-store"]);
  });

  it("explains an unavailable finished output without inventing a URL", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) return json(issuance(false));
      return json({ detail: "Not found." }, 404);
    }));
    renderApp(`/issuances/${ISSUANCE_ID}`);

    expect(await screen.findByText("Kết quả PDF hiện không có sẵn. Hãy kiểm tra trạng thái công việc hoặc tạo bản cấp phát mới.")).toBeVisible();
    expect(screen.queryByRole("heading", { name: "Bản cấp phát đã sẵn sàng" })).not.toBeInTheDocument();
    expect(screen.queryByRole("button", { name: "Tải PDF kết quả" })).not.toBeInTheDocument();
  });

  it("keeps download errors safe and retryable", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) return json(issuance(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}/result`) return json({ code: "STORAGE_UNAVAILABLE" }, 503);
      return json({ detail: "Not found." }, 404);
    }));
    renderApp(`/issuances/${ISSUANCE_ID}`);

    fireEvent.click(await screen.findByRole("button", { name: "Tải PDF kết quả" }));
    expect(await screen.findByRole("alert")).toHaveTextContent("Không thể tạo liên kết tải lúc này. Hãy thử lại.");
    expect(screen.getByRole("button", { name: "Thử tải lại" })).toBeVisible();
  });

  it("removes a stale download action when the server reports permanent unavailability", async () => {
    let detailReads = 0;
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      const path = new URL(request.url).pathname;
      if (path === "/api/v1/auth/session") return json(session("issuer"));
      if (path === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) {
        detailReads += 1;
        return json(issuance(detailReads === 1));
      }
      if (path === `/api/v1/issuances/${ISSUANCE_ID}/result`) {
        return json({ code: "ISSUANCE_RESULT_UNAVAILABLE" }, 409);
      }
      return json({ detail: "Not found." }, 404);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp(`/issuances/${ISSUANCE_ID}`);

    fireEvent.click(await screen.findByRole("button", { name: "Tải PDF kết quả" }));

    expect(await screen.findByText("Kết quả PDF hiện không có sẵn. Hãy kiểm tra trạng thái công việc hoặc tạo bản cấp phát mới.")).toBeVisible();
    await waitFor(() => expect(detailReads).toBe(2));
    expect(screen.queryByRole("button", { name: /tải/i })).not.toBeInTheDocument();
    expect(screen.queryByText("Hãy thử lại.")).not.toBeInTheDocument();
  });

  it("renders recipient email and optional full name fields instead of recipient UUID", async () => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async (input) => {
      const request = input instanceof Request ? input : new Request(input);
      return new URL(request.url).pathname === "/api/v1/auth/session"
        ? json(session("issuer"))
        : json({ detail: "Unexpected request." }, 500);
    });
    vi.stubGlobal("fetch", fetchMock);
    renderApp();

    expect(await screen.findByLabelText(/Email người nhận/i)).toBeInTheDocument();
    expect(screen.getByLabelText(/Họ và tên/i)).toBeInTheDocument();
    expect(screen.getByText(/Không bắt buộc/i)).toBeInTheDocument();
    expect(screen.queryByLabelText("Mã người nhận")).not.toBeInTheDocument();
    expect(screen.queryByPlaceholderText("Dán mã người nhận được cấp")).not.toBeInTheDocument();
  });

  it("submits recipient_email and recipient_name to the issuance API without recipient_id", async () => {
    const observed: ObservedRequest[] = [];
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
      if (url.pathname === "/api/v1/demo/capabilities") return json(demoCapabilities(true));
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
        return json({
          id: JOB_ID,
          kind: "issuance",
          status: "processing",
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
    fireEvent.change(screen.getByLabelText(/Email người nhận/i), { target: { value: "student@example.com" } });
    fireEvent.change(screen.getByLabelText(/Họ và tên/i), { target: { value: "Nguyễn Văn A" } });
    fireEvent.submit(screen.getByRole("button", { name: "Tạo bản cấp phát" }).closest("form")!);

    expect(await screen.findByText("Đang xử lý")).toBeVisible();

    const issuanceReq = observed.find((r) => r.path === "/api/v1/issuances");
    expect(issuanceReq).toBeDefined();
    expect(issuanceReq?.body).toEqual({
      recipient_email: "student@example.com",
      recipient_name: "Nguyễn Văn A",
      upload_id: UPLOAD_ID,
      correlation_id: expect.stringMatching(/^[0-9a-f-]{36}$/),
    });
    expect((issuanceReq?.body as Record<string, unknown>).recipient_id).toBeUndefined();
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
