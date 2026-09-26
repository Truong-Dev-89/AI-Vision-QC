# AI Vision QC — Khung dự án đa sản phẩm

## Giao diện web có camera trực tiếp

```bash
uvicorn api.app:app --reload --port 8000
```

Mở trình duyệt vào **http://127.0.0.1:8000/ui/** — giao diện cho phép:
- Bật webcam/camera, xem hình trực tiếp
- Chọn sản phẩm, nhập/quét mã SN, bấm "Chụp & Kiểm tra"
- Thấy ngay ảnh đã khoanh đỏ vùng lỗi (nếu có) và kết quả đạt/nghi ngờ/lỗi
- Chuyển sang tab "Quét hàng trả về" để đối chiếu theo mã SN (xem mục bên dưới)
- Xác nhận Tốt/Lỗi ngay trên giao diện để AI học tiếp

## Đối chiếu 2 lần quét: xuất hàng vs khách trả về (vòng lặp tự học chính)

```
Xuất hàng: POST /inspect/<product_id>  (kèm serial=<mã_SN>)  -> log lại kết quả theo SN
Khách trả về: POST /return-scan/<product_id>  (kèm serial=<mã_SN>)  -> tự tìm lại log cũ
```

- Nếu **lúc xuất: đạt** nhưng **lúc trả về: AI phát hiện lỗi** → bằng chứng rõ ràng
  là lỗi bị bỏ sót thật. Hệ thống **tự động** thêm vào `confirmed_ng/`, không cần
  người xác nhận lại — đây là dữ liệu quý nhất để giảm hàng NG lọt ra ngoài.
- Nếu **lúc trả về AI vẫn thấy bình thường** → hệ thống **không tự** gán nhãn,
  vì có thể là lỗi chức năng (camera không thấy) hoặc hư hỏng khi vận chuyển.
  Cần người xác nhận thủ công qua `POST /feedback` nếu muốn đưa vào dữ liệu train.

## Triển khai nhiều trạm camera cùng gọi vào 1 máy chủ

Khi 1 máy chạy API phục vụ nhiều trạm khác trong xưởng (không chỉ chạy 1 mình
trên `127.0.0.1` nữa), có 2 việc BẮT BUỘC phải làm:

### 1. Lấy API key

Khi chạy `uvicorn`, terminal sẽ in ra dòng dạng:
```
API KEY của trạm này: xxxxxxxxxxxxxxxxxxxxxxxxxxxx
```
Mỗi trạm mở `/ui/`, dán đúng khóa này vào ô "API key" ở đầu trang, bấm "Lưu khóa" —
chỉ cần làm 1 lần cho mỗi trình duyệt. Khóa được lưu trong file `.api_key` ở
thư mục gốc dự án — **không đẩy file này lên git** (đã có sẵn trong `.gitignore`).

### 2. Bật HTTPS (bắt buộc để camera hoạt động qua mạng)

Trình duyệt CHỈ cho phép trang web dùng camera nếu truy cập qua `localhost`
HOẶC qua HTTPS — không có ngoại lệ. Nếu các trạm khác truy cập bằng địa chỉ IP
qua HTTP thường, camera sẽ **không bao giờ bật được**, dù mã nguồn đúng 100%.

Tạo chứng chỉ tự ký (chạy 1 lần, cần có OpenSSL — có sẵn nếu bạn cài Git for
Windows):
```powershell
openssl req -x509 -newkey rsa:2048 -keyout key.pem -out cert.pem -days 365 -nodes -subj "/CN=vision-qc-local"
```

Chạy server với HTTPS, cho phép máy khác trong mạng gọi vào (`--host 0.0.0.0`):
```powershell
uvicorn api.app:app --host 0.0.0.0 --port 8000 --ssl-keyfile key.pem --ssl-certfile cert.pem
```

Các trạm khác truy cập qua: `https://<địa-chỉ-IP-máy-chủ>:8000/ui/`
(ví dụ `https://192.168.1.50:8000/ui/`). Trình duyệt sẽ cảnh báo "Not secure"
vì chứng chỉ tự ký — đây là bình thường trong mạng nội bộ, bấm "Advanced" →
"Proceed" để tiếp tục, chỉ cần làm 1 lần trên mỗi trạm.

**Không mở port này ra internet** (không port-forward trên router) — hệ thống
chỉ thiết kế cho mạng nội bộ nhà máy.

## Cách chạy thật (đã có code, không còn là khung rỗng)

```bash
# 1. Cài thư viện (máy cần có kết nối mạng để tải PyTorch + pretrained weights)
pip install -r requirements.txt

# 2. Bỏ ảnh "tốt" vào đúng thư mục (tối thiểu 20-30 ảnh)
#    data/raw/<product_id>/good/anh1.jpg, anh2.jpg, ...

# 3. Train — thực chất là xây "ngân hàng đặc trưng" từ ảnh tốt
python training/train.py --product <product_id>
#    -> in ra đường dẫn model + ngưỡng đề xuất

# 4. Copy configs/products/_template.yaml -> configs/products/<product_id>.yaml
#    điền model.path và decision.threshold theo kết quả bước 3

# 5. Chạy API để kiểm tra ảnh qua HTTP
uvicorn api.app:app --reload --port 8000
#    POST /inspect/<product_id>            (kèm file ảnh) -> kết quả pass/suspect/reject
#    POST /feedback/<product_id>/<image_id>?is_good=true|false  -> AI ghi nhận, chuẩn bị tự học
```

## Vòng lặp "tự học" hoạt động thế nào
Mỗi ảnh bị đánh dấu `suspect`/`reject` được tự động lưu vào `data/raw/<product_id>/suspect/`.
Khi bạn gọi `/feedback` xác nhận đúng/sai, ảnh được chuyển vào `good/` (nếu AI báo nhầm)
hoặc `confirmed_ng/` (nếu đúng là lỗi). Khi đủ số ảnh mới (`min_new_samples` trong config),
chạy lại `training/train.py` — model sẽ học thêm từ chính những ảnh đó, theo đúng quy trình
kiểm soát version an toàn ở `docs/retrain_policy.md`.

---

## Nguyên tắc cốt lõi (thiết kế thư mục)
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
