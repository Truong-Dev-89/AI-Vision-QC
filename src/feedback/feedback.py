"""
Vòng lặp tự học. Đây là phần biến hệ thống từ "kiểm tra cố định" thành
"càng dùng càng chính xác":

  ảnh nghi ngờ / bị công nhân sửa kết quả
        -> lưu vào đúng thư mục data/raw/<product_id>/
        -> đủ số lượng mới (min_new_samples trong config)
        -> nhắc/trigger chạy lại training/train.py
"""
from __future__ import annotations
import json
import shutil
from datetime import datetime
from pathlib import Path

from src.utils.config import resolve_path, load_product_config


def _log_path(product_id: str) -> Path:
    p = resolve_path(f"data/logs/feedback_{product_id}.jsonl")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def record_result(product_id: str, image_path: Path, score: float, decision: str,
                   serial: str | None = None) -> None:
    """Ghi lại MỌI kết quả kiểm tra, kể cả 'pass'.
    Lý do: khi có hàng bị khách trả lại, cần tra lại đúng ảnh + điểm số lúc
    xuất xưởng để biết model đã bỏ sót lỗi này hay chưa (false negative thật)."""
    entry = {
        "time": datetime.now().isoformat(timespec="seconds"),
        "product_id": product_id,
        "serial": serial,
        "score": score,
        "decision": decision,
        "image": str(image_path),
    }
    with open(_log_path(product_id), "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, ensure_ascii=False) + "\n")


def save_suspect(product_id: str, image_path: Path) -> Path:
    dest_dir = resolve_path(f"data/raw/{product_id}/suspect")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / image_path.name
    shutil.copy(image_path, dest)
    return dest


def confirm_feedback(product_id: str, image_path: Path, is_good: bool) -> Path:
    """Người vận hành xác nhận đúng/sai cho 1 ảnh.
    Tốt -> thêm vào good/ (ngân hàng đặc trưng phong phú hơn ở lần train sau).
    Lỗi -> confirmed_ng/ (ưu tiên dùng khi đánh giá model mới trước khi thay
    thế model đang chạy — xem docs/retrain_policy.md)."""
    target = "good" if is_good else "confirmed_ng"
    dest_dir = resolve_path(f"data/raw/{product_id}/{target}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / image_path.name
    shutil.copy(image_path, dest)
    return dest


def find_shipment_record(product_id: str, serial: str) -> dict | None:
    """Tìm lần quét gần nhất của đúng mã SN trong log — dùng để đối chiếu khi
    hàng bị khách trả về, xem lúc xuất hàng AI đã kết luận thế nào."""
    log_file = _log_path(product_id)
    if not serial or not log_file.exists():
        return None
    matches = []
    with open(log_file, "r", encoding="utf-8") as f:
        for line in f:
            entry = json.loads(line)
            if entry.get("serial") == serial:
                matches.append(entry)
    return matches[-1] if matches else None


def should_retrain(product_id: str) -> dict:
    """So số ảnh mới (suspect + confirmed_ng) với ngưỡng min_new_samples
    trong config sản phẩm để quyết định có nên chạy lại train.py hay chưa."""
    cfg = load_product_config(product_id)
    min_new = cfg.get("retrain", {}).get("min_new_samples", 50)
    suspect_dir = resolve_path(f"data/raw/{product_id}/suspect")
    ng_dir = resolve_path(f"data/raw/{product_id}/confirmed_ng")
    count = sum(1 for d in (suspect_dir, ng_dir) if d.exists() for _ in d.glob("*"))
    return {"new_samples": count, "min_required": min_new, "should_retrain": count >= min_new}
