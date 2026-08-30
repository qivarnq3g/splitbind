import { readFileSync } from "node:fs";
import { resolve } from "node:path";

import { describe, expect, it } from "vitest";

describe("production and offline asset boundary", () => {
  it("keeps the HTML entry point free of third-party runtime assets", () => {
    const html = readFileSync(resolve(process.cwd(), "index.html"), "utf8");
    expect(html).not.toMatch(/(?:src|href)=["']https?:\/\//i);
  });
});
