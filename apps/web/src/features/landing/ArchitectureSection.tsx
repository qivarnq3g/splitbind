export function ArchitectureSection() {
  return (
    <section
      className="landing-section"
      data-landing-section="06"
      aria-labelledby="architecture"
    >
      <div className="landing-section-body">
        <p className="landing-eyebrow">06</p>
        <h2 id="architecture">Hệ thống dựng bằng gì</h2>
        <p>
          Các thành phần được chia theo vai trò tách bạch, để khối xử lý nặng
          không nằm chung với khối phục vụ giao diện.
        </p>
        <dl className="landing-stack">
          <div>
            <dt>React và Vite</dt>
            <dd>
              Giao diện chạy trong trình duyệt, viết bằng React và đóng gói bằng
              Vite.
            </dd>
          </div>
          <div>
            <dt>Django REST</dt>
            <dd>
              Tầng điều phối: xác thực phiên, phân quyền theo tổ chức và ghi nhận
              bằng chứng cấp phát.
            </dd>
          </div>
          <div>
            <dt>Hàng đợi xử lý bất đồng bộ</dt>
            <dd>
              Dựng bản cấp phát và xác minh đều chạy nền, tách khỏi yêu cầu của
              trình duyệt.
            </dd>
          </div>
          <div>
            <dt>PostgreSQL</dt>
            <dd>Nơi lưu hồ sơ cấp phát, hồ sơ xác minh và nhật ký chỉ ghi thêm.</dd>
          </div>
          <div>
            <dt>Lưu trữ đối tượng</dt>
            <dd>
              Tệp gốc và tệp đã cấp phát nằm ở đây, chỉ mở bằng liên kết có thời
              hạn ngắn.
            </dd>
          </div>
          <div>
            <dt>Caddy</dt>
            <dd>
              Đứng ở biên, nhận kết nối đã mã hóa từ trình duyệt rồi chuyển tiếp
              vào các dịch vụ bên trong.
            </dd>
          </div>
        </dl>
      </div>
    </section>
  );
}
