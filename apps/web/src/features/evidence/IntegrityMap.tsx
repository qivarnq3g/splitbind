import type { components } from "../../api/generated/schema";

type Region = components["schemas"]["SuspiciousRegion"];

type Props = {
  regions?: Region[];
  pageGeometry?: { width: number; height: number };
};

export function IntegrityMap({ regions, pageGeometry }: Props) {
  const canRender = Boolean(pageGeometry && pageGeometry.width > 0 && pageGeometry.height > 0 && regions && regions.length > 0);
  return (
    <section className="integrity-map" aria-labelledby="integrity-map-title">
      <div className="evidence-section-heading">
        <h3 id="integrity-map-title">Vùng toàn vẹn nghi vấn</h3>
        <span className="map-legend"><span aria-hidden="true" /> Tín hiệu vùng nghi vấn</span>
      </div>
      {canRender ? (
        <svg className="integrity-canvas" viewBox={`0 0 ${pageGeometry!.width} ${pageGeometry!.height}`} role="img" aria-label="Bản đồ các vùng toàn vẹn nghi vấn">
          <rect className="page-outline" width={pageGeometry!.width} height={pageGeometry!.height} />
          {regions!.map((region, index) => (
            <rect
              className="suspicious-region"
              key={`${region.x}-${region.y}-${index}`}
              x={region.x * pageGeometry!.width}
              y={region.y * pageGeometry!.height}
              width={region.width * pageGeometry!.width}
              height={region.height * pageGeometry!.height}
            />
          ))}
        </svg>
      ) : (
        <p className="map-unavailable">
          {regions
            ? "API chưa cung cấp trang tương ứng và hình học từng trang để đặt chính xác các vùng, nên giao diện không vẽ bản đồ suy đoán."
            : "API chưa cung cấp danh sách vùng nghi vấn và hình học từng trang, nên giao diện không vẽ bản đồ suy đoán."}
        </p>
      )}
      <p className="technical-notice">Đây là tín hiệu kỹ thuật, không phải kết luận pháp lý.</p>
    </section>
  );
}
