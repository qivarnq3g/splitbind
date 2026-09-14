export function VerificationSection() {
  return (
    <section
      className="landing-section"
      data-landing-section="04"
      aria-labelledby="verification"
    >
      <div className="landing-section-body">
        <p className="landing-eyebrow">04</p>
        <h2 id="verification">Tệp nghi vấn, đặt cạnh hồ sơ gốc</h2>
        <p>
          Bạn tải lên tệp nghi vấn. Đó có thể là bản PDF, mà cũng có thể chỉ là
          một tấm ảnh chụp màn hình ai đó gửi cho bạn.
        </p>
        <p>
          Hệ thống làm hai việc tách rời nhau. Trước hết nó tính mã băm của tệp
          và tìm xem có bản cấp phát nào trùng khít từng byte hay không. Nếu
          không trùng, nó đọc thủy vân nằm trong ảnh để tìm xem tệp này bắt
          nguồn từ bản cấp phát nào.
        </p>
        <p>
          Nhờ vậy hai câu hỏi được trả lời riêng. Tệp này từ đâu ra, và tệp này
          có còn nguyên như lúc phát hành không. Một tệp đã bị nén lại hay bị thu
          nhỏ thì mã băm chắc chắn khác, nhưng vẫn có thể truy ra nguồn.
        </p>
        <p>
          Những gì hệ thống chưa kết luận được thì nêu riêng, kèm cả hai giá trị
          mã băm để bạn tự đối chiếu, thay vì gộp tất cả vào một phán quyết
          chung.
        </p>
      </div>
    </section>
  );
}
