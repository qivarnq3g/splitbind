import { describe, expect, it } from "vitest";

import {
  UNKNOWN_PAGE_COUNT,
  countPdfPages,
} from "../features/uploads/pdfPageCount";

function pdf(body: string): File {
  return new File([body], "probe.pdf", { type: "application/pdf" });
}

describe("counting PDF pages in the browser", () => {
  it("counts page objects and ignores the page tree node", async () => {
    const body =
      "%PDF-1.7\n" +
      "1 0 obj<</Type/Pages/Count 3/Kids[2 0 R 3 0 R 4 0 R]>>endobj\n" +
      "2 0 obj<</Type/Page/Parent 1 0 R>>endobj\n" +
      "3 0 obj<</Type /Page/Parent 1 0 R>>endobj\n" +
      "4 0 obj<</Type/Page>>endobj\n";

    expect(await countPdfPages(pdf(body))).toBe(3);
  });

  it("does not mistake other Page-prefixed keys for a page", async () => {
    const body =
      "1 0 obj<</Type/Page>>endobj\n" +
      "2 0 obj<</Type/PageLabel/S/D>>endobj\n" +
      "3 0 obj<</Type/Pages/Count 1>>endobj\n";

    expect(await countPdfPages(pdf(body))).toBe(1);
  });

  it("reports an unknown count when the page objects are compressed away", async () => {
    const body = "%PDF-1.7\nstream\n\u0001\u0002\u0003binary\nendstream\n";

    expect(await countPdfPages(pdf(body))).toBe(UNKNOWN_PAGE_COUNT);
  });
});
