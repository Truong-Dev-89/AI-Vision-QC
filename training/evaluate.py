"""
Compare a newly trained model against the one currently in production,
following the safe-retraining procedure in docs/retrain_policy.md — only
promote the new model when it does not miss more real defects and does not
falsely reject more good units.

Usage:
    python training/evaluate.py --product <product_id> --candidate models/<product_id>/v2/bank.pt

Requires that the candidate's sibling meta.json (written by train.py) sits
next to the bank.pt file, and that data/raw/<product_id>/confirmed_ng/ has
at least a few images of real, confirmed defects.
"""
import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from src.inference.engine import PatchCoreEngine
from src.utils.config import load_product_config, resolve_path
from src.evaluation import compute_rates, verdict

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def _score_all(engine: PatchCoreEngine, image_paths: list[Path]) -> list[float]:
    return [engine.score(Image.open(p))["score"] for p in image_paths]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", required=True, help="product_id, khớp tên thư mục trong data/raw/")
    ap.add_argument("--candidate", required=True, help="Đường dẫn tới bank.pt của model mới cần đánh giá")
    args = ap.parse_args()

    cfg = load_product_config(args.product)
    current_path = resolve_path(cfg["model"]["path"])
    current_threshold = cfg["decision"]["threshold"]

    candidate_path = Path(args.candidate)
    candidate_meta_path = candidate_path.parent / "meta.json"
    if not candidate_meta_path.exists():
        sys.exit(f"Không tìm thấy {candidate_meta_path} — cần file meta.json ghi ra từ train.py.")
    candidate_threshold = json.loads(candidate_meta_path.read_text())["threshold"]

    good_dir = resolve_path(f"data/raw/{args.product}/good")
    ng_dir = resolve_path(f"data/raw/{args.product}/confirmed_ng")
    good_images = sorted(p for p in good_dir.glob("*") if p.suffix.lower() in IMG_EXT)
    ng_images = sorted(p for p in ng_dir.glob("*") if p.suffix.lower() in IMG_EXT)

    print(f"[1/3] Đang chấm điểm {len(good_images)} ảnh tốt + {len(ng_images)} ảnh lỗi đã xác nhận bằng model HIỆN TẠI...")
    current_engine = PatchCoreEngine.load(current_path)
    current_good_scores = _score_all(current_engine, good_images)
    current_ng_scores = _score_all(current_engine, ng_images)
    current_rates = compute_rates(current_good_scores, current_ng_scores, current_threshold)

    print(f"[2/3] Đang chấm điểm cùng bộ ảnh bằng model MỚI ({candidate_path})...")
    candidate_engine = PatchCoreEngine.load(candidate_path)
    candidate_good_scores = _score_all(candidate_engine, good_images)
    candidate_ng_scores = _score_all(candidate_engine, ng_images)
    candidate_rates = compute_rates(candidate_good_scores, candidate_ng_scores, candidate_threshold)

    print("[3/3] Kết quả so sánh:\n")
    print(f"{'':20}{'Hiện tại':>15}{'Model mới':>15}")
    print(f"{'Escape rate':20}{current_rates['escape_rate']:>15.2%}{candidate_rates['escape_rate']:>15.2%}"
          if current_rates["escape_rate"] is not None else "Escape rate: không đủ dữ liệu confirmed_ng/ để so sánh")
    print(f"{'False positive rate':20}{current_rates['false_positive_rate']:>15.2%}{candidate_rates['false_positive_rate']:>15.2%}")
    print()
    print(verdict(current_rates, candidate_rates))


if __name__ == "__main__":
    main()
