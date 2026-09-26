"""
Save an annotated NG (defect) image and write a lookup log per day.

Storage layout:
  data/logs/ng_images/<product_id>/<YYYY-MM-DD>/<SN>.jpg   — annotated image
  data/logs/ng_log/<product_id>/<YYYY-MM-DD>.csv           — lookup log for that day

Why split by day and name files by serial number: when a customer returns a
unit, knowing just the serial number + shipping date is enough to instantly
find the inspection image, instead of searching through thousands of files.
"""
from __future__ import annotations
import csv
from datetime import datetime
from pathlib import Path

from PIL import Image

from src.utils.config import resolve_path


def _ng_image_dir(product_id: str, date_str: str) -> Path:
    d = resolve_path(f"data/logs/ng_images/{product_id}/{date_str}")
    d.mkdir(parents=True, exist_ok=True)
    return d


def _ng_csv_path(product_id: str, date_str: str) -> Path:
    p = resolve_path(f"data/logs/ng_log/{product_id}/{date_str}.csv")
    p.parent.mkdir(parents=True, exist_ok=True)
    return p


def save_ng(product_id: str, annotated_image: Image.Image, serial: str | None,
            score: float, threshold: float, decision: str) -> Path:
    now = datetime.now()
    date_str = now.strftime("%Y-%m-%d")
    safe_serial = (serial or "").strip() or f"unknown_{now.strftime('%H%M%S%f')}"

    dest_dir = _ng_image_dir(product_id, date_str)
    dest = dest_dir / f"{safe_serial}.jpg"
    counter = 1
    while dest.exists():  # avoid overwriting if the same SN is scanned/inspected more than once in a day
        dest = dest_dir / f"{safe_serial}_{counter}.jpg"
        counter += 1
    annotated_image.convert("RGB").save(dest, quality=92)

    csv_path = _ng_csv_path(product_id, date_str)
    is_new = not csv_path.exists()
    with open(csv_path, "a", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow(["time", "serial", "decision", "score", "threshold", "image_path"])
        writer.writerow([now.isoformat(timespec="seconds"), serial or "", decision,
                          f"{score:.4f}", f"{threshold:.4f}", str(dest)])
    return dest
