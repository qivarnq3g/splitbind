import "@testing-library/jest-dom/vitest";

import { QueryClientProvider } from "@tanstack/react-query";
import { cleanup, render, screen, within } from "@testing-library/react";
import { RouterProvider, createMemoryRouter } from "react-router-dom";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

import { createQueryClient } from "../app/queryClient";
import { appRoutes } from "../app/router";
import { EvidenceSummary } from "../features/evidence/EvidenceSummary";
import { LIMITATION_COPY, STATUS_COPY, STATUS_LIMITATIONS } from "../features/evidence/copy";

const USER_ID = "00000000-0000-4000-8000-000000000001";
const ORGANIZATION_ID = "00000000-0000-4000-8000-000000000002";
const VERIFICATION_ID = "00000000-0000-4000-8000-000000000007";
const ISSUANCE_ID = "00000000-0000-4000-8000-000000000008";
const JOB_ID = "00000000-0000-4000-8000-000000000006";

function jsonResponse(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), { status, headers: { "Content-Type": "application/json" } });
}

function mockSession(role = "verifier") {
  return {
    authenticated: true,
    csrf_token: "csrf-token",
    user: { id: USER_ID, username: `${role}.demo`, role, organization_id: ORGANIZATION_ID },
  };
}

function renderAppPath(path: string) {
  const router = createMemoryRouter(appRoutes, { initialEntries: [path] });
  return render(
    <QueryClientProvider client={createQueryClient()}>
      <RouterProvider router={router} />
    </QueryClientProvider>
  );
}

const statuses = [
  "VERIFIED_INTACT",
  "SOURCE_IDENTIFIED_MODIFIED",
  "PARTIAL_EVIDENCE",
  "NO_WATERMARK",
  "INVALID_MANIFEST",
  "PROCESSING_FAILED",
] as const;

afterEach(cleanup);

describe("verification evidence language", () => {
  it.each(statuses)("keeps the conclusion visible and technical evidence collapsed for %s", (status) => {
    render(<EvidenceSummary status={status} evidence={{}} />);
    expect(screen.getByText(STATUS_COPY[status].inference)).toBeVisible();
    const details = screen.getByText("Xem chi tiết kỹ thuật").closest("details");
    expect(details).not.toHaveAttribute("open");
    expect(screen.getByRole("heading", { name: "Dữ liệu kỹ thuật" })).toBeInTheDocument();
    expect(screen.getByRole("heading", { name: "Giới hạn của kết quả" })).toBeInTheDocument();
    for (const limitationId of STATUS_LIMITATIONS[status]) {
      expect(screen.getAllByText(LIMITATION_COPY[limitationId]!)).not.toHaveLength(0);
    }
  });

  it.each([
    ["NO_WATERMARK", "không có nghĩa tài liệu chắc chắn không thuộc hệ thống"],
    ["PARTIAL_EVIDENCE", "chưa đủ ngưỡng để gán nguồn phát hành"],
    ["SOURCE_IDENTIFIED_MODIFIED", "không chứng minh người nhận đã sửa, làm rò rỉ hoặc phát tán"],
  ] as const)("renders mandatory limitation copy for %s", (status, copy) => {
    render(<EvidenceSummary status={status} evidence={{}} />);
    expect(screen.getByText(new RegExp(copy, "i"))).toBeInTheDocument();
  });

  it("shows only a safe generic message for an unknown limitation identifier", () => {
    render(<EvidenceSummary status="INVALID_MANIFEST" evidence={{ limitations: ["private.backend.detail"] }} />);
    expect(screen.queryByText("private.backend.detail")).not.toBeInTheDocument();
    expect(screen.getByText("Kết quả có thêm giới hạn kỹ thuật chưa được giao diện mô tả chi tiết.")).toBeInTheDocument();
  });

  it("keeps the unreleased fingerprint warning when the API reports it", () => {
    render(<EvidenceSummary
      status="PARTIAL_EVIDENCE"
      evidence={{ limitations: ["fingerprint.experimental_unreleased_v2"] }}
    />);

    expect(screen.getByText(LIMITATION_COPY["fingerprint.experimental_unreleased_v2"]!)).toBeInTheDocument();
  });

  it("explains a non-exact integrity result without claiming a watermark search", () => {
    render(<EvidenceSummary
      status="NO_WATERMARK"
      evidence={{
        algorithm_label: "integrity_release_v1",
        exact_file_hash_match: false,
        limitations: ["fingerprint.transformed_attribution_unavailable"],
      }}
    />);

    expect(screen.getByText(/Không tìm thấy bản cấp phát có mã SHA-256 trùng/)).toBeVisible();
    expect(screen.getByText(/Không định vị vùng chỉnh sửa/)).toBeInTheDocument();
    expect(screen.queryByText(STATUS_COPY.NO_WATERMARK.inference)).not.toBeInTheDocument();
  });

  it("does not turn an omitted suspicious-region field into a zero count", () => {
    render(<EvidenceSummary status="NO_WATERMARK" evidence={{}} />);
    const fact = screen.getByText("Số vùng nghi vấn").parentElement!;
    expect(within(fact).getByText("API chưa cung cấp")).toBeInTheDocument();
    expect(within(fact).queryByText("0")).not.toBeInTheDocument();
  });
});

describe("authoritative result payoff and seal construction", () => {
  beforeEach(() => {
    document.cookie = "csrftoken=csrf-token";
  });

  afterEach(() => {
    cleanup();
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
  });

  it("presents an intact verdict before technical evidence", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") return jsonResponse(mockSession("verifier"));
      if (path === `/api/v1/verifications/${VERIFICATION_ID}`) {
        return jsonResponse({
          id: VERIFICATION_ID,
          job_id: JOB_ID,
          job_status: "succeeded",
          status: "VERIFIED_INTACT",
          created_at: "2026-08-30T12:01:00Z",
          completed_at: "2026-08-30T12:03:00Z",
          evidence: {
            algorithm_label: "candidate_v1",
            decode_status: "decoded",
            fingerprint_confidence: 0.98,
            integrity_score: 1.0,
            valid_vote_count: 32,
            analyzed_page_count: 5,
            manifest_signature_valid: true,
            exact_file_hash_match: true,
            suspicious_regions: [],
            limitations: [],
          },
          metrics: { processing_ms: 120 },
        });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    }));

    renderAppPath(`/verifications/${VERIFICATION_ID}`);

    const verdict = await screen.findByRole("region", { name: "Kết luận kiểm chứng" });
    expect(verdict).toHaveTextContent("Đã xác minh toàn vẹn");
    expect(verdict).toHaveAttribute("data-tone", "success");
    expect(screen.getByText("Xem chi tiết kỹ thuật").closest("details")).not.toHaveAttribute("open");

  });

  it("distinguishes modified source evidence from a legal accusation", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") return jsonResponse(mockSession("verifier"));
      if (path === `/api/v1/verifications/${VERIFICATION_ID}`) {
        return jsonResponse({
          id: VERIFICATION_ID,
          job_id: JOB_ID,
          job_status: "succeeded",
          status: "SOURCE_IDENTIFIED_MODIFIED",
          created_at: "2026-08-30T12:01:00Z",
          completed_at: "2026-08-30T12:03:00Z",
          evidence: {
            algorithm_label: "candidate_v1",
            decode_status: "decoded",
            fingerprint_confidence: 0.75,
            integrity_score: 0.42,
            valid_vote_count: 18,
            analyzed_page_count: 5,
            manifest_signature_valid: true,
            exact_file_hash_match: false,
            suspicious_regions: [{ x: 0.1, y: 0.2, width: 0.3, height: 0.15 }],
            limitations: ["match_not_actor_proof"],
          },
          metrics: { processing_ms: 150 },
        });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    }));

    renderAppPath(`/verifications/${VERIFICATION_ID}`);

    const verdict = await screen.findByRole("region", { name: "Kết luận kiểm chứng" });
    expect(verdict).toHaveTextContent("Khớp nguồn, có dấu hiệu thay đổi");
    expect(verdict).toHaveAttribute("data-tone", "warning");
    expect(verdict).toHaveTextContent("không xác định người thực hiện");

  });

  it("makes the completed issuance artifact available as the primary action", async () => {
    vi.stubGlobal("fetch", vi.fn<typeof globalThis.fetch>(async (input) => {
      const path = new URL(input instanceof Request ? input.url : String(input)).pathname;
      if (path === "/api/v1/auth/session") return jsonResponse(mockSession("issuer"));
      if (path === `/api/v1/issuances/${ISSUANCE_ID}`) {
        return jsonResponse({
          id: ISSUANCE_ID,
          job_id: JOB_ID,
          status: "succeeded",
          issued_at: "2026-08-30T12:01:00Z",
          result_available: true,
          algorithm_label: "candidate_v1",
        });
      }
      return jsonResponse({ detail: "Not found" }, 404);
    }));

    renderAppPath(`/issuances/${ISSUANCE_ID}`);

    expect(await screen.findByRole("heading", { name: "Bản cấp phát đã sẵn sàng" })).toBeVisible();
    expect(screen.getByRole("button", { name: "Tải PDF kết quả" })).toBeEnabled();
    expect(screen.getByText("Thử nghiệm — chưa phát hành")).toBeVisible();

  });
});
