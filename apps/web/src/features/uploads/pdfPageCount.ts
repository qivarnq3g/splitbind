export const UNKNOWN_PAGE_COUNT = -1;

const PAGE_OBJECT = /\/Type\s*\/Page(?![sA-Za-z])/g;

export async function countPdfPages(file: File): Promise<number> {
  try {
    const bytes = new Uint8Array(await file.arrayBuffer());
    let text = "";
    const step = 0x8000;
    for (let start = 0; start < bytes.length; start += step) {
      text += String.fromCharCode(...bytes.subarray(start, start + step));
    }
    const matches = text.match(PAGE_OBJECT);
    return matches && matches.length > 0 ? matches.length : UNKNOWN_PAGE_COUNT;
  } catch {
    return UNKNOWN_PAGE_COUNT;
  }
}
