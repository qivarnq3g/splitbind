const UNITS = ["KB", "MB", "GB", "TB"] as const;
const STEP = 1000;

export function formatBytes(bytes: number): string {
  if (!Number.isFinite(bytes) || bytes < 0) return "0 B";
  if (bytes < STEP) return `${Math.round(bytes)} B`;

  let value = bytes / STEP;
  let unit = 0;
  while (value >= STEP && unit < UNITS.length - 1) {
    value /= STEP;
    unit += 1;
  }

  const digits = value < 10 ? 1 : 0;
  const shown = value.toLocaleString("vi-VN", {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits,
  });
  return `${shown} ${UNITS[unit]}`;
}
