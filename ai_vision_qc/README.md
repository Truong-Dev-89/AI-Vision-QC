# AI Vision QC — Khung dự án đa sản phẩm

## Nguyên tắc cốt lõi
Hệ thống được thiết kế theo 2 lớp tách biệt, để thêm sản phẩm mới KHÔNG cần sửa mã nguồn lõi:

1. **Lớp nền tảng (`src/`)**: xử lý ảnh, chạy model, ra quyết định, tích hợp PLC/MES.
   Dùng chung cho mọi sản phẩm, hiếm khi thay đổi.
2. **Lớp cấu hình (`configs/products/`)**: mỗi sản phẩm là 1 file YAML riêng,
   trỏ đến model, dữ liệu, ngưỡng của chính nó.

Khi có sản phẩm mới: thêm 1 thư mục trong `data/raw/`, train model, thêm 1 file
YAML trong `configs/products/` — không đụng vào `src/`.

## Cấu trúc thư mục

```
ai_vision_qc/
├── configs/products/     # 1 file YAML = 1 loại sản phẩm
├── data/
│   ├── raw/<product_id>/{good,suspect,confirmed_ng}/
│   ├── processed/        # ảnh đã tiền xử lý, sẵn sàng train
│   └── logs/             # shipment_log.csv, returns_log.csv
├── models/<product_id>/  # trọng số đã train, có version
├── src/
│   ├── capture/          # giao tiếp camera, trigger chụp
│   ├── preprocessing/    # crop theo ROI, căn chỉnh, chuẩn hóa
│   ├── inference/        # load model, tính điểm bất thường
│   ├── decision/         # logic đạt/lỗi/nghi ngờ theo ngưỡng
│   ├── feedback/         # vòng lặp tự học: gán nhãn, trigger retrain
│   ├── integration/      # kết nối PLC/MES
│   └── utils/            # hàm dùng chung
├── training/             # script train, đánh giá model
├── api/                  # REST API phục vụ inference real-time
├── dashboard/            # giao diện giám sát tỷ lệ lỗi
├── tests/                # kiểm thử tự động
├── deployment/
│   ├── docker/           # đóng gói triển khai server
│   └── edge/             # cấu hình cho Jetson/thiết bị biên
└── docs/                 # tài liệu vận hành, runbook
```

## Quy tắc đặt tên (giữ nguyên xuyên suốt dự án)
- `product_id`: chữ thường, không dấu, gạch dưới. Ví dụ: `bo_mach_a`, `bao_bi_nhua_b`
- Ảnh: `<ma_lo>_<serial>.jpg`, ví dụ `LO20260924_SP00015.jpg`
- Model: `models/<product_id>/v<số phiên bản>/model.pt`, ví dụ `models/bo_mach_a/v3/model.pt`

## Luồng thêm 1 sản phẩm mới
1. Tạo `data/raw/<product_id>/good/` và bỏ ảnh tốt vào
2. Chạy `training/train.py --product <product_id>` để train
3. Copy `configs/products/_template.yaml` → `configs/products/<product_id>.yaml`, điền thông số
4. Hệ thống lõi tự nhận diện sản phẩm mới qua file cấu hình, không cần deploy lại `src/`

## Vòng lặp tự học (feedback loop)
`src/feedback/` chịu trách nhiệm: mọi ảnh bị gắn cờ "nghi ngờ" hoặc bị công nhân
sửa lại kết quả sẽ tự động được lưu vào `data/raw/<product_id>/suspect/`.
Định kỳ (tuần/tháng), chạy lại `training/train.py` để cập nhật model — xem
`docs/retrain_policy.md` để biết quy trình kiểm soát version an toàn.
