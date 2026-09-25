# training/

train.py: train model cho 1 product_id từ ảnh trong data/raw/<product_id>/good/
evaluate.py: đánh giá model mới so với model đang chạy production trước khi
thay thế (tránh rollback thủ công khi model mới tệ hơn).
