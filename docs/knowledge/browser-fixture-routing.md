# Browser fixture routing

Playwright navigation can invalidate a previous Response body before response.json runs (Network.getResponseBody: No resource with given identifier). For a real API response that immediately triggers document/download navigation, capture through route.fetch and read its body before route.fulfill with the unchanged response. This preserves real server behavior while preventing the evidence-capture race; do not replace it with fabricated fixture success.

Windows CLI JSON filtering: a gh --jq expression with an embedded quoted string arrived with the quotes stripped and reported an undefined jq function. Prefer gh --json piped into PowerShell ConvertFrom-Json, then native object filtering and ConvertTo-Json for concise output. This avoids nested shell/JQ quote interpretation without weakening checks.

The shell harness may reject a combined recursive Remove-Item operation before execution. Validate exact task-owned paths and reparse boundaries first; the workspace lifecycle guide documents native .NET exact-target deletion. In the verified case that mechanism removed only selected disposable outputs, with requested screenshots copied separately first.

Keep capabilities/session reads separate from the upload workflow trace. Progressive-disclosure tests must activate the summary before checking hidden evidence. For resource-constrained runs, investigate worker-start timeouts separately from application assertions; a validated Vitest `--maxWorkers=1` run preserves coverage without ignoring errors. Reset document scroll before full-page screenshots to avoid misleading positions of offscreen fixed elements. Video extraction can return blank frames despite successful tooling; visually inspect outputs before claiming motion evidence and bound frame callbacks.

For exact full-file patches, UTF-8 BOM must remain in the old-text anchor. PowerShell Get-Content hides the BOM; Node readFileSync with JSON transport preserves it. Patch hunks must be ordered by their location in the file. The apply_patch implementation rejects delete+add on one path in the same patch; use separately validated operations for an authorized full replacement.

When testing a Vite app with Playwright request fixtures, a broad `**/api/**` glob can intercept `/src/api/client.ts` and prevent application modules loading. Target the actual namespace such as `**/api/v1/**`. Diagnose a blank page using browser console and module responses before changing app authentication. Await screenshot production before opening files from a running capture process.
