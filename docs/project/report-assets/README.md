# Ảnh dùng cho báo cáo

Hai loại ảnh, để riêng vì chúng có vòng đời khác nhau.

## `figures/`

Tám ảnh được nhúng thẳng vào báo cáo. Danh sách và chú thích nằm trong biến `FIGURES`
của `build_report_v2.py`; đổi tên tệp ở đây thì phải sửa cả biến đó.

| Tệp | Nguồn |
|---|---|
| `ui-issuance-result.png` | Chụp từ hệ thống đang vận hành |
| `ui-verification-match.png` | Chụp từ hệ thống đang vận hành |
| `ui-verification-no-match.png` | Chụp từ hệ thống đang vận hành |
| `ui-verification-traced.png` | Chụp từ hệ thống đang vận hành |
| `chart-v1-vs-v3.png` | `make_figures.py` dựng từ dữ liệu đo |
| `chart-attack-envelope.png` | `make_figures.py` dựng từ dữ liệu đo |
| `chart-frame-restore.png` | `make_figures.py` dựng từ dữ liệu đo |
| `chart-carrier-decides.png` | `make_figures.py` dựng từ dữ liệu đo |

Ba biểu đồ là tệp sinh ra, chạy `python make_figures.py` để dựng lại. Ba ảnh giao diện
là tệp chụp tay, phải chụp lại mỗi khi chữ trên giao diện đổi, nếu không ảnh sẽ mâu thuẫn
với phần chữ trong báo cáo.

## `evidence/`

Ảnh chụp hệ thống thật để làm bằng chứng, không nhúng vào báo cáo. Bộ mới nhất là
`2026-09-15-v0.2.3/`; các bộ trước giữ lại để đối chiếu trạng thái theo từng bản phát hành. Mỗi lần chụp là một
thư mục đặt tên theo ngày và bản phát hành được chụp, kèm `README.md` ghi rõ chụp cái gì
và vào lúc nào. Giữ lại các lần chụp cũ thay vì ghi đè, vì chúng là bằng chứng về trạng
thái hệ thống tại đúng thời điểm đó.
