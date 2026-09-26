"""
The self-learning feedback loop. This is what turns the system from "fixed
inspection" into "gets more accurate the more it's used":

  a suspect image / an image whose verdict a worker corrects
        -> saved into the right data/raw/<product_id>/ subfolder
        -> enough new samples accumulate (min_new_samples in the config)
        -> prompts/triggers re-running training/train.py
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
    """Log EVERY inspection result, including 'pass' ones.
    Why: when a customer returns a unit, we need to look up the exact image +
    score from shipping time to tell whether the model truly missed a real
    defect (a genuine false negative)."""
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
    """A human confirms whether an image was correctly judged.
    Good -> add to good/ (enriches the memory bank on the next training run).
    Defect -> confirmed_ng/ (used first when evaluating a new model before it
    replaces the one in production — see docs/retrain_policy.md)."""
    target = "good" if is_good else "confirmed_ng"
    dest_dir = resolve_path(f"data/raw/{product_id}/{target}")
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / image_path.name
    shutil.copy(image_path, dest)
    return dest


def find_shipment_record(product_id: str, serial: str) -> dict | None:
    """Look up the most recent scan for a given serial number — used to
    cross-check against a returned unit and see what the AI concluded at
    shipping time."""
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
    """Compare the number of new images (suspect + confirmed_ng) against the
    min_new_samples threshold in the product's config to decide whether it's
    time to re-run train.py."""
    cfg = load_product_config(product_id)
    min_new = cfg.get("retrain", {}).get("min_new_samples", 50)
    suspect_dir = resolve_path(f"data/raw/{product_id}/suspect")
    ng_dir = resolve_path(f"data/raw/{product_id}/confirmed_ng")
    count = sum(1 for d in (suspect_dir, ng_dir) if d.exists() for _ in d.glob("*"))
    return {"new_samples": count, "min_required": min_new, "should_retrain": count >= min_new}
