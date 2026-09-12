const SUFFIX = "SplitBind";

const TITLES: ReadonlyArray<readonly [RegExp, string]> = [
  [/^\/about$/, "Giới thiệu hệ thống"],
  [/^\/login$/, "Đăng nhập"],
  [/^\/issue$/, "Cấp phát tài liệu"],
  [/^\/verify$/, "Xác minh tài liệu"],
  [/^\/history$/, "Lịch sử xử lý"],
  [/^\/jobs\/[^/]+$/, "Tiến độ xử lý"],
  [/^\/issuances\/[^/]+$/, "Hồ sơ cấp phát"],
  [/^\/verifications\/[^/]+$/, "Kết quả kiểm chứng"],
];

export function titleForPath(pathname: string): string {
  if (pathname === "/") return `${SUFFIX} · Truy vết toàn vẹn văn bản`;
  const match = TITLES.find(([pattern]) => pattern.test(pathname));
  return match ? `${match[1]} · ${SUFFIX}` : `Không tìm thấy trang · ${SUFFIX}`;
}
