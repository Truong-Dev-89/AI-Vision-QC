"""
Minimal API serving the production line: inspect images + record feedback
for the self-learning loop.

Run:
    uvicorn api.app:app --reload --port 8000

Main endpoints:
    POST /inspect/{product_id}              — upload an image (with a form
                                               field 'serial', the barcode/QR
                                               scanned serial number), returns
                                               the inspection result
    POST /feedback/{product_id}/{image_id}  — confirm whether a past
                                               inspection was right or wrong
    GET  /products                          — list of products that have a config

When the result is suspect/reject:
    - the original image is saved to data/raw/<product_id>/suspect/ (training data for later)
    - the annotated (red-boxed) image is saved to
      data/logs/ng_images/<product_id>/<YYYY-MM-DD>/<SN>.jpg
    - a daily lookup log is appended to data/logs/ng_log/<product_id>/<YYYY-MM-DD>.csv
"""
import base64
import io
import os
import secrets
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from fastapi import Depends, FastAPI, File, Form, Header, HTTPException, UploadFile
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

# --- API key authentication ---
# Only strictly necessary once this server is called by multiple stations
# over the network. If you only ever run it alone on 127.0.0.1, this key
# matters less, but it's still good practice to keep it enabled.
_KEY_FILE = Path(__file__).resolve().parents[1] / ".api_key"


def _get_or_create_api_key() -> str:
    env_key = os.environ.get("VISION_QC_API_KEY")
    if env_key:
        return env_key
    if _KEY_FILE.exists():
        return _KEY_FILE.read_text().strip()
    key = secrets.token_urlsafe(24)
    _KEY_FILE.write_text(key)
    return key


API_KEY = _get_or_create_api_key()
print("=" * 60)
print(f"API KEY của trạm này: {API_KEY}")
print("Mỗi trạm camera cần nhập đúng khóa này ở giao diện /ui/ để dùng được.")
print("Không chia sẻ khóa này ra ngoài phạm vi nhà máy.")
print("=" * 60)


def verify_api_key(x_api_key: str | None = Header(None)) -> None:
    if x_api_key != API_KEY:
        raise HTTPException(401, "Sai hoặc thiếu API key (gửi kèm header X-API-Key).")


_AUTH = [Depends(verify_api_key)]

# Lets the web UI (dashboard/) call the API even when opened from another
# address on the same factory network. If deploying beyond the internal
# network, restrict allow_origins instead of leaving it as "*".
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

_DASHBOARD_DIR = Path(__file__).resolve().parents[1] / "dashboard"
app.mount("/ui", StaticFiles(directory=str(_DASHBOARD_DIR), html=True), name="ui")


@app.get("/")
async def root():
    """Redirect anyone hitting the bare root URL to the actual UI at /ui/."""
    from fastapi.responses import RedirectResponse
    return RedirectResponse(url="/ui/")
_engines: dict[str, PatchCoreEngine] = {}


def get_engine(product_id: str) -> tuple[PatchCoreEngine, dict]:
    cfg = load_product_config(product_id)
    if product_id not in _engines:
        model_path = resolve_path(cfg["model"]["path"])
        if not model_path.exists():
            raise HTTPException(404, f"Chưa có model đã train cho '{product_id}'. Chạy training/train.py trước.")
        _engines[product_id] = PatchCoreEngine.load(model_path)
    return _engines[product_id], cfg


@app.post("/inspect/{product_id}", dependencies=_AUTH)
async def inspect(product_id: str, file: UploadFile = File(...),
                   serial: str | None = Form(None, description="Serial number scanned from a barcode/QR scanner")):
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


@app.post("/feedback/{product_id}/{image_id}", dependencies=_AUTH)
async def submit_feedback(product_id: str, image_id: str, is_good: bool):
    image_path = resolve_path(f"data/logs/images/{product_id}/{image_id}")
    if not image_path.exists():
        raise HTTPException(404, "Không tìm thấy ảnh — kiểm tra lại image_id trả về từ /inspect.")
    dest = fb.confirm_feedback(product_id, image_path, is_good)
    return {"saved_to": str(dest), "retrain": fb.should_retrain(product_id)}


@app.post("/return-scan/{product_id}", dependencies=_AUTH)
async def return_scan(product_id: str, file: UploadFile = File(...),
                       serial: str = Form(..., description="Serial number of the unit returned by the customer")):
    """
    Re-scan a unit returned by a customer and cross-check it against its
    outbound (shipment-time) scan by serial number.

    - If the AI said 'pass' at shipment but this return scan detects a
      defect -> clear evidence the model missed a real defect (an escape).
      Automatically added to confirmed defect data, high priority for the
      next retraining run.
    - If the return scan still looks fine -> do NOT auto-label anything,
      since this could be a non-visual (functional) defect or damage that
      happened during shipping, not a manufacturing defect. A human should
      confirm via POST /feedback before it's added to the dataset.
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
        response["note"] = "No shipment scan found for this serial number in the log — cannot cross-check automatically."
        return response

    escaped = original["decision"] == "pass" and decision.value != "pass"
    response["escaped_defect"] = escaped

    if escaped:
        annotated = draw_defect_box(image, result["heatmap"], result["grid"], threshold)
        ng_path = ng_logger.save_ng(product_id, annotated, serial, result["score"], threshold, "escaped_defect")
        fb.confirm_feedback(product_id, saved_path, is_good=False)
        response["action"] = "Automatically added to confirmed defect data — high priority for the next retraining run."
        response["ng_image_saved_to"] = str(ng_path)
        buf = io.BytesIO()
        annotated.save(buf, format="JPEG", quality=90)
        response["annotated_image_base64"] = base64.b64encode(buf.getvalue()).decode("ascii")
    else:
        response["action"] = ("No visible evidence of a defect. If the customer confirms the unit is genuinely "
                               "defective, use POST /feedback to label it manually (likely a functional defect "
                               "or shipping damage).")

    return response


@app.get("/stats/{product_id}")
async def get_stats(product_id: str):
    """Today's inspection counts: total, pass, suspect, reject."""
    import json as _json
    from datetime import date

    log_file = resolve_path(f"data/logs/feedback_{product_id}.jsonl")
    counts = {"pass": 0, "suspect": 0, "reject": 0}
    today = date.today().isoformat()
    if log_file.exists():
        with open(log_file, "r", encoding="utf-8") as f:
            for line in f:
                entry = _json.loads(line)
                if entry.get("time", "").startswith(today):
                    d = entry.get("decision")
                    if d in counts:
                        counts[d] += 1
    total = sum(counts.values())
    return {"date": today, "total": total, **counts}


@app.get("/products")
async def get_products():
    return {"products": list_products()}
