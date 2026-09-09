import "@testing-library/jest-dom/vitest";

import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { appRoutes } from "../app/router";
import { createQueryClient } from "../app/queryClient";
import { validatePdf, validateVerificationFile } from "../features/uploads/uploadIssuance";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const UPLOAD_ID = "00000000-0000-4000-8000-000000000004";
const VERIFICATION_ID = "00000000-0000-4000-8000-000000000007";
const JOB_ID = "00000000-0000-4000-8000-000000000006";
const PDF_SHA256 = "4f1949e95440af0ece666ebd5f399c1d77d22de639950784d349fa5feb47dca5";

type Role = "administrator" | "issuer" | "verifier" | "auditor";
type ObservedRequest = { path: string; credentials: RequestCredentials; headers: Headers; body: unknown };

function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function session(role: Role) {
  return {
    authenticated: true,
    csrf_token: "csrf-token",
    user: { id: USER_ID, username: `${role}.demo`, role, organization_id: ORGANIZATION_ID },
  };
}

function renderApp(path = "/verify") {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(<QueryClientProvider client={createQueryClient()}><RouterProvider router={router} /></QueryClientProvider>);
}

function job(status: "processing" | "failed" | "cancelled") {
  return {
    id: JOB_ID, kind: "verification", status, attempt: 0,
    issuance_id: null, verification_id: VERIFICATION_ID,
    deadline_at: "2026-08-30T12:11:00Z",
    cancel_requested_at: status === "cancelled" ? "2026-08-30T12:02:00Z" : null,
    safe_error_code: status === "failed" ? "INPUT_INVALID" : null,
    created_at: "2026-08-30T12:01:00Z", updated_at: "2026-08-30T12:02:00Z",
  };
}

describe("verification browser workflow", () => {
  beforeEach(() => { document.cookie = "csrftoken=csrf-token"; });
  afterEach(() => { cleanup(); vi.restoreAllMocks(); vi.unstubAllGlobals(); });

  it("hashes, uploads without credentials, finalizes, creates, and follows a verification job", async () => {
    const observed: ObservedRequest[] = [];
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input, init) => {
      const request = input instanceof Request && init === undefined ? input : new Request(input, init);
      const url = new URL(request.url);
      const text = request.method === "GET" ? "" : await request.clone().text();
      const parsed = text && request.headers.get("content-type")?.includes("application/json") ? JSON.parse(text) as unknown : text || null;
      observed.push({ path: url.pathname, credentials: request.credentials, headers: request.headers, body: parsed });
      if (url.pathname === "/api/v1/auth/session") return json(session("verifier"));
      if (url.pathname === "/api/v1/uploads") return json({
        id: UPLOAD_ID, object_key: "uploads/orphan/verification.pdf", expected_sha256: PDF_SHA256,
        size_bytes: 14, expires_at: "2026-08-30T12:15:00Z", finalized_at: null,
        upload_url: "https://storage.example.test/direct-upload",
        required_headers: { "Content-Type": "application/pdf", "x-amz-meta-sha256": PDF_SHA256 },
      }, 201);
      if (url.hostname === "storage.example.test") return new Response(null, { status: 200 });
      if (url.pathname === `/api/v1/uploads/${UPLOAD_ID}/complete`) return json({
        id: UPLOAD_ID, object_key: "uploads/orphan/verification.pdf", expected_sha256: PDF_SHA256,
        size_bytes: 14, expires_at: "2026-08-30T12:15:00Z", finalized_at: "2026-08-30T12:01:00Z",
      });
      if (url.pathname === "/api/v1/verifications") return json({
        id: VERIFICATION_ID, job_id: JOB_ID, job_status: "created", status: null,
        created_at: "2026-08-30T12:01:00Z", completed_at: null, evidence: {}, metrics: {},
      }, 201);
      if (url.pathname === `/api/v1/jobs/${JOB_ID}`) return json(job("processing"));
      return json({ detail: "Unexpected request." }, 500);
    }));

    renderApp();
    expect(await screen.findByText("Tải tài liệu lên để xem kết quả kiểm tra kỹ thuật.")).toBeVisible();
    fireEvent.change(await screen.findByLabelText("Tệp cần kiểm chứng"), {
      target: { files: [new File(["%PDF-1.4\n%%EOF"], "suspect.pdf", { type: "application/pdf" })] },
    });
    fireEvent.submit(screen.getByRole("button", { name: "Bắt đầu xác minh" }).closest("form")!);
    expect(await screen.findByText("Đang xử lý")).toBeVisible();

    const workflow = observed.filter((request) => ![
      "/api/v1/auth/session",
      "/api/v1/demo/capabilities",
    ].includes(request.path));
    expect(workflow.map((request) => request.path)).toEqual([
      "/api/v1/uploads", "/direct-upload", `/api/v1/uploads/${UPLOAD_ID}/complete`,
      "/api/v1/verifications", `/api/v1/jobs/${JOB_ID}`,
    ]);
    expect(workflow[0]?.body).toEqual({ kind: "verification_input", filename: "suspect.pdf", content_type: "application/pdf", size_bytes: 14, sha256: PDF_SHA256 });
    expect(workflow[1]?.credentials).toBe("omit");
    expect(Object.fromEntries(workflow[1]!.headers.entries())).toMatchObject({ "content-type": "application/pdf", "x-amz-meta-sha256": PDF_SHA256 });
    expect(workflow[2]?.body).toEqual({ sha256: PDF_SHA256 });
    expect(workflow[3]?.body).toEqual({ upload_id: UPLOAD_ID, correlation_id: expect.stringMatching(/^[0-9a-f-]{36}$/) });
  });

  it.each(["issuer", "auditor"] as const)("does not let %s create a verification", async (role) => {
    const fetchMock = vi.fn<typeof globalThis.fetch>(async () => json(session(role)));
    vi.stubGlobal("fetch", fetchMock);
    renderApp();
    expect(await screen.findByRole("heading", { name: "Không có quyền tạo kiểm chứng" })).toBeVisible();
    expect(screen.queryByLabelText("Tệp cần kiểm chứng")).not.toBeInTheDocument();
    await waitFor(() => expect(fetchMock).toHaveBeenCalledTimes(2));
  });

  it("lets an administrator create a verification, matching the backend policy", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json(session("administrator"))));
    renderApp();
    expect(await screen.findByLabelText("Tệp cần kiểm chứng")).toBeVisible();
  });

  it("makes a selected verification file replaceable before upload", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async () => json(session("verifier"))));
    renderApp();
    const fileInput = await screen.findByLabelText("Tệp cần kiểm chứng");
    fireEvent.change(fileInput, { target: { files: [new File(["%PDF-1.4"], "suspect.pdf", { type: "application/pdf" })] } });
    expect(screen.getByText("suspect.pdf")).toBeVisible();
    expect(screen.getByText("Tệp được chọn trên thiết bị")).toBeVisible();
    fireEvent.click(screen.getByRole("button", { name: "Bỏ tệp đã chọn" }));
    expect(screen.queryByText("suspect.pdf")).not.toBeInTheDocument();
    expect(screen.getByText("Chưa chọn tệp")).toBeVisible();
  });

  it("accepts PDF, PNG, and JPEG verification inputs without weakening issuance validation", () => {
    expect(() => validateVerificationFile(new File(["pdf"], "sample.pdf", { type: "application/pdf" }))).not.toThrow();
    expect(() => validateVerificationFile(new File(["png"], "sample.png", { type: "image/png" }))).not.toThrow();
    expect(() => validateVerificationFile(new File(["jpg"], "sample.jpg", { type: "image/jpeg" }))).not.toThrow();
    expect(() => validateVerificationFile(new File(["gif"], "sample.gif", { type: "image/gif" }))).toThrow(/PDF, PNG hoặc JPEG/);
    expect(() => validatePdf(new File(["png"], "sample.png", { type: "image/png" }))).toThrow(/không phải PDF/);
  });

  it("renders contract facts without recipient disclosure or invented geometry", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") return json(session("verifier"));
      return json({
        id: VERIFICATION_ID, job_id: JOB_ID, job_status: "succeeded", status: "SOURCE_IDENTIFIED_MODIFIED",
        created_at: "2026-08-30T12:01:00Z", completed_at: "2026-08-30T12:03:00Z",
        evidence: {
          fingerprint_confidence: 0.75, integrity_score: 0.5, valid_vote_count: 9, analyzed_page_count: 3,
          manifest_signature_valid: true, exact_file_hash_match: false,
          suspicious_regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.1 }],
          limitations: ["fingerprint.experimental_unreleased_v2", "fingerprint.not_gate_g1_evidence", "evidence.not_proof_of_leak_edit_or_distribution", "integrity.not_evaluated"],
        }, metrics: { processing_ms: 25 },
      });
    }));
    renderApp(`/verifications/${VERIFICATION_ID}`);
    expect(await screen.findByRole("heading", { name: "Khớp nguồn, có dấu hiệu thay đổi" })).toBeVisible();
    fireEvent.click(screen.getByText("Xem chi tiết kỹ thuật"));
    expect(screen.getByText("Demo không đánh giá watermark toàn vẹn hoặc định vị vùng chỉnh sửa.")).toBeVisible();
    expect(screen.getByText("0,75")).toBeVisible();
    expect(screen.getByText("API chưa cung cấp trang tương ứng và hình học từng trang", { exact: false })).toBeVisible();
    expect(screen.queryByText(/giới hạn kỹ thuật chưa được giao diện mô tả/)).not.toBeInTheDocument();
    expect(document.body).not.toHaveTextContent(/mã người nhận:\s*[0-9a-f-]{36}/i);
  });

  it("labels a non-exact integrity result as an exact-file mismatch", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") return json(session("verifier"));
      return json({
        id: VERIFICATION_ID, job_id: JOB_ID, job_status: "succeeded", status: "NO_WATERMARK",
        created_at: "2026-08-30T12:01:00Z", completed_at: "2026-08-30T12:03:00Z",
        evidence: {
          algorithm_label: "integrity_release_v1",
          exact_file_hash_match: false,
          limitations: ["fingerprint.transformed_attribution_unavailable"],
        },
        metrics: { processing_ms: 25 },
      });
    }));

    renderApp(`/verifications/${VERIFICATION_ID}`);

    expect(await screen.findByRole("heading", { name: "Không khớp file đã cấp phát" })).toBeVisible();
    expect(screen.getByText("Tệp không khớp chính xác với bản đã cấp phát.")).toBeVisible();
    fireEvent.click(screen.getByText("Xem chi tiết kỹ thuật"));
    expect(screen.getByText("Nhận diện fingerprint sau biến đổi chưa khả dụng.")).toBeVisible();
  });

  it("shows a safe scoped denial for a foreign verification", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      return path === "/api/v1/auth/session" ? json(session("auditor")) : json({ detail: "Not found." }, 404);
    }));
    renderApp(`/verifications/${VERIFICATION_ID}`);
    expect(await screen.findByRole("alert", {}, { timeout: 3_000 })).toHaveTextContent("Không tìm thấy dữ liệu trong phạm vi được cấp quyền");
    expect(document.body).not.toHaveTextContent("Not found");
  });

  it.each([
    ["failed", "Thất bại", "INPUT_INVALID"],
    ["cancelled", "Đã hủy", null],
  ] as const)("renders a terminal %s verification job", async (status, label, errorCode) => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      return path === "/api/v1/auth/session" ? json(session("verifier")) : json(job(status));
    }));
    renderApp(`/jobs/${JOB_ID}`);
    expect(await screen.findByRole("heading", { name: label })).toBeVisible();
    expect(screen.getByRole("link", { name: "Mở hồ sơ kiểm chứng" })).toHaveAttribute("href", `/verifications/${VERIFICATION_ID}`);
    if (errorCode) expect(screen.getByRole("alert")).toHaveTextContent(errorCode);
  });

  it.each([
    ["failed", "Công việc xử lý thất bại nên không có bằng chứng kiểm chứng."],
    ["dead_lettered", "Công việc xử lý thất bại nên không có bằng chứng kiểm chứng."],
    ["cancelled", "Công việc đã bị hủy nên không có kết quả kiểm chứng."],
  ] as const)("does not call a terminal %s verification pending", async (jobStatus, expected) => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") return json(session("verifier"));
      return json({
        id: VERIFICATION_ID, job_id: JOB_ID, job_status: jobStatus, status: null,
        created_at: "2026-08-30T12:01:00Z", completed_at: null, evidence: {}, metrics: {},
      });
    }));
    renderApp(`/verifications/${VERIFICATION_ID}`);
    expect(await screen.findByText(expected)).toBeVisible();
    expect(screen.queryByText(/Bằng chứng sẽ xuất hiện/)).not.toBeInTheDocument();
  });
});
