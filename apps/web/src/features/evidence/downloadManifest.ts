import { getIssuanceManifest } from "../issuances/issuances";

export async function downloadIssuanceManifest(issuanceId: string): Promise<void> {
  const bundle = await getIssuanceManifest(issuanceId);
  const text = JSON.stringify(bundle, null, 2);
  const url = URL.createObjectURL(
    new Blob([text], { type: "application/json" }),
  );
  const anchor = document.createElement("a");
  anchor.href = url;
  anchor.download = `splitbind-manifest-${issuanceId}.json`;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  URL.revokeObjectURL(url);
}
