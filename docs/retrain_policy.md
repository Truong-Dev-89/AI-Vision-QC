# Quy trình retrain an toàn (tránh model mới tệ hơn model cũ)

1. Model mới train xong lưu vào `models/<product_id>/v<n+1>/`, KHÔNG ghi đè
   `models/<product_id>/v<n>/` đang chạy production.
2. Chạy `training/evaluate.py` so sánh model mới với model cũ trên tập dữ liệu
   `confirmed_ng/` + `good/` mới nhất.
3. Chỉ chuyển sang model mới khi: escape rate (bỏ sót lỗi) không tăng VÀ
   false positive rate không tăng đáng kể.
4. Cập nhật `model.path` trong file config của sản phẩm sang version mới.
5. Giữ lại ít nhất 2 version gần nhất để rollback nếu phát hiện vấn đề sau
   khi lên production.

## Ưu tiên dữ liệu khi retrain
Dữ liệu từ hàng bị khách trả về (false negative thật) luôn được ưu tiên
đưa vào tập train trước, vì đây là loại lỗi có tác động kinh doanh trực tiếp
nhất — xem lại mục tiêu ban đầu: giảm hàng NG lọt ra ngoài đến khách hàng.
