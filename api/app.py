"""
API tối thiểu phục vụ dây chuyền: kiểm tra ảnh + ghi nhận phản hồi để tự học.

Chạy thử:
    uvicorn api.app:app --reload --port 8000

Endpoint chính:
    POST /inspect/{product_id}              — tải ảnh lên (kèm form field 'serial'
                                               là mã SN quét từ máy quét mã vạch/QR),
                                               trả kết quả kiểm tra
    POST /feedback/{product_id}/{image_id}  — xác nhận đúng/sai cho 1 ảnh đã kiểm tra
    GET  /products                          — danh sách sản phẩm đã có cấu hình

Khi kết quả là suspect/reject:
    - ảnh gốc lưu vào data/raw/<product_id>/suspect/  (dữ liệu để retrain sau)
    - ảnh đã khoanh đỏ vùng lỗi lưu vào
      data/logs/ng_images/<product_id>/<YYYY-MM-DD>/<SN>.jpg
    - log tra cứu theo ngày ghi vào data/logs/ng_log/<product_id>/<YYYY-MM-DD>.csv
"""
import base64
import io
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from PIL import Image

from src.decision.decision import decide
from src.feedback import feedback as fb
from src.feedback import ng_logger
from src.inference.engine import PatchCoreEngine
from src.inference.visualize import draw_defect_box
from src.utils.config import list_products, load_product_config, resolve_path

app = FastAPI(title="Vision QC API")

# Cho phép giao diện web (dashboard/) gọi API dù mở từ địa chỉ khác trên cùng
# mạng nội bộ nhà máy. Nếu triển khai ra ngoài internet, nên giới hạn lại
# allow_origins thay vì để "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard"
app.mount("/ui", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="ui")
_engines: dict[str, PatchCoreEngine] = {}


def get_engine(product_id: str) -> tuple[PatchCoreEngine, dict]:
    cfg = load_product_config(product_id)
    if product_id not in _engines:
        model_path = resolve_path(cfg["model"]["path"])
        if not model_path.exists():
            raise HTTPException(404, f"Chưa có model đã train cho '{product_id}'. Chạy training/train.py trước.")
        _engines[product_id] = PatchCoreEngine.load(model_path)
    return _engines[product_id], cfg


@app.post("/inspect/{product_id}")
async def inspect(product_id: str, file: UploadFile = File(...),
                   serial: str | None = Form(None, description="Mã SN quét từ máy quét mã vạch/QR")):
    engine, cfg = get_engine(product_id)
    raw = await file.read()
    image = Image.open(io.BytesIO(raw))

    save_dir = resolve_path(f"data/logs/images/{product_id}")
    save_dir.mkdir(parents=True, exist_ok=True)
    saved_path = save_dir / f"{uuid.uuid4().hex}_{file.filename}"
    image.convert("RGB").save(saved_path)

    result = engine.score(image)
    threshold = cfg["decision"]["threshold"]
    margin = cfg["decision"].get("suspect_margin", 0.15)
    decision = decide(result["score"], threshold, margin)

    fb.record_result(product_id, saved_path, result["score"], decision.value, serial=serial)

    response = {
        "product_id": product_id,
        "serial": serial,
        "score": result["score"],
        "threshold": threshold,
        "decision": decision.value,
        "image_id": saved_path.name,
    }

    if decision.value != "pass":
        fb.save_suspect(product_id, saved_path)
        annotated = draw_defect_box(image, result["heatmap"], result["grid"], threshold)
        ng_path = ng_logger.save_ng(product_id, annotated, serial, result["score"], threshold, decision.value)
        response["ng_image_saved_to"] = str(ng_path)
        buf = io.BytesIO()
        annotated.save(buf, format="JPEG", quality=90)
        response["annotated_image_base64"] = base64.b64encode(buf.getvalue()).decode("ascii")

    return response


@app.post("/feedback/{product_id}/{image_id}")
async def submit_feedback(product_id: str, image_id: str, is_good: bool):
    image_path = resolve_path(f"data/logs/images/{product_id}/{image_id}")
    if not image_path.exists():
        raise HTTPException(404, "Không tìm thấy ảnh — kiểm tra lại image_id trả về từ /inspect.")
    dest = fb.confirm_feedback(product_id, image_path, is_good)
    return {"saved_to": str(dest), "retrain": fb.should_retrain(product_id)}


@app.post("/return-scan/{product_id}")
async def return_scan(product_id: str, file: UploadFile = File(...),
                       serial: str = Form(..., description="Mã SN của hàng bị khách trả về")):
    """
    Quét lại hàng bị khách trả về, đối chiếu với lần quét xuất hàng theo mã SN.

    - Lúc xuất hàng AI báo 'pass' nhưng lần quét trả về này lại phát hiện lỗi
      -> bằng chứng rõ ràng đây là lỗi bị bỏ sót thật (escape). Tự động thêm
      vào dữ liệu lỗi đã xác nhận, ưu tiên cao cho lần retrain tiếp theo.
    - Lần quét trả về vẫn không thấy gì bất thường -> KHÔNG tự động gán nhãn,
      vì đây có thể là lỗi chức năng (camera không thấy được) hoặc hư hỏng
      phát sinh khi vận chuyển, không phải lỗi từ lúc sản xuất. Cần người
      xác nhận qua POST /feedback nếu muốn đưa vào dữ liệu.
    """
    engine, cfg = get_engine(product_id)
    raw = await file.read()
    image = Image.open(io.BytesIO(raw))

    result = engine.score(image)
    threshold = cfg["decision"]["threshold"]
    margin = cfg["decision"].get("suspect_margin", 0.15)
    decision = decide(result["score"], threshold, margin)
    original = fb.find_shipment_record(product_id, serial)

    save_dir = resolve_path(f"data/logs/images/{product_id}")
    save_dir.mkdir(parents=True, exist_ok=True)
    saved_path = save_dir / f"return_{uuid.uuid4().hex}_{file.filename}"
    image.convert("RGB").save(saved_path)

    response = {
        "product_id": product_id,
        "serial": serial,
        "return_scan_score": result["score"],
        "return_scan_decision": decision.value,
        "original_shipment_found": original is not None,
        "original_decision": original["decision"] if original else None,
    }

    if original is None:
        response["note"] = "Không tìm thấy lần quét xuất hàng của mã SN này trong log — không thể tự đối chiếu."
        return response

    escaped = original["decision"] == "pass" and decision.value != "pass"
    response["escaped_defect"] = escaped

    if escaped:
        annotated = draw_defect_box(image, result["heatmap"], result["grid"], threshold)
        ng_path = ng_logger.save_ng(product_id, annotated, serial, result["score"], threshold, "escaped_defect")
        fb.confirm_feedback(product_id, saved_path, is_good=False)
        response["action"] = "Tự động thêm vào dữ liệu lỗi đã xác nhận — ưu tiên cao cho lần retrain tới."
        response["ng_image_saved_to"] = str(ng_path)
        buf = io.BytesIO()
        annotated.save(buf, format="JPEG", quality=90)
        response["annotated_image_base64"] = base64.b64encode(buf.getvalue()).decode("ascii")
    else:
        response["action"] = ("Không có bằng chứng lỗi nhìn thấy được. Nếu khách xác nhận sản phẩm thực sự lỗi, "
                               "dùng POST /feedback để gán nhãn thủ công (khả năng lỗi chức năng hoặc hư hỏng vận chuyển).")

    return response


@app.get("/products")
async def get_products():
    return {"products": list_products()}
