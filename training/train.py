"""
Training — really means BUILDING THE MEMORY BANK from "good" images (no
defect images needed).

Usage:
    python training/train.py --product ten_san_pham

Prerequisite: good images already placed in data/raw/ten_san_pham/good/
(recommended minimum 20-30 images, more is more stable).

The --offline-test flag is for testing the code when there is NO internet
access to download pretrained weights (uses a randomly-initialized backbone
instead) — do NOT use this flag for production, results will be inaccurate.
"""
import argparse
import json
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from PIL import Image

from src.inference.engine import PatchCoreEngine
from src.utils.config import resolve_path

IMG_EXT = {".jpg", ".jpeg", ".png", ".bmp"}


def next_version(model_dir: Path) -> int:
    existing = [int(p.name[1:]) for p in model_dir.glob("v*") if p.name[1:].isdigit()]
    return (max(existing) + 1) if existing else 1


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--product", required=True, help="product_id, khớp tên thư mục trong data/raw/")
    ap.add_argument("--good-dir", default=None, help="Ghi đè thư mục ảnh tốt (mặc định data/raw/<product>/good)")
    ap.add_argument("--holdout", type=float, default=0.2, help="Tỉ lệ ảnh tốt dùng để tự kiểm tra ngưỡng")
    ap.add_argument("--k", type=float, default=2.0, help="Hệ số độ lệch chuẩn khi tính ngưỡng (cao hơn = ít nhạy hơn)")
    ap.add_argument("--offline-test", action="store_true", help="Chạy thử không cần tải pretrained weights")
    args = ap.parse_args()

    good_dir = Path(args.good_dir) if args.good_dir else resolve_path(f"data/raw/{args.product}/good")
    images = sorted(p for p in good_dir.glob("*") if p.suffix.lower() in IMG_EXT)
    if len(images) < 5:
        sys.exit(f"Cần ít nhất 5 ảnh tốt trong {good_dir}, hiện có {len(images)}.")

    print(f"[1/4] Nạp backbone (pretrained={not args.offline_test})...")
    engine = PatchCoreEngine(pretrained=not args.offline_test)

    n_holdout = max(1, int(len(images) * args.holdout))
    holdout_imgs, train_imgs = images[:n_holdout], images[n_holdout:]
    if len(train_imgs) < 3:
        train_imgs, holdout_imgs = images, images[:1]

    print(f"[2/4] Xây ngân hàng đặc trưng từ {len(train_imgs)} ảnh...")
    engine.build_memory_bank(train_imgs)

    print(f"[3/4] Tính ngưỡng phát hiện từ {len(holdout_imgs)} ảnh giữ lại...")
    scores = [engine.score(Image.open(p))["score"] for p in holdout_imgs]
    mean = sum(scores) / len(scores)
    variance = sum((s - mean) ** 2 for s in scores) / len(scores)
    threshold = mean + args.k * (variance ** 0.5) + 1e-6

    model_dir = resolve_path(f"models/{args.product}")
    version = next_version(model_dir)
    out_dir = model_dir / f"v{version}"
    engine.save(out_dir / "bank.pt")

    meta = {
        "product_id": args.product,
        "version": version,
        "trained_at": datetime.now().isoformat(timespec="seconds"),
        "num_train_images": len(train_imgs),
        "num_holdout_images": len(holdout_imgs),
        "threshold": threshold,
        "holdout_scores": scores,
    }
    (out_dir / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[4/4] Xong. Model: {out_dir / 'bank.pt'}  ·  ngưỡng đề xuất: {threshold:.4f}")
    print(f"      Cập nhật configs/products/{args.product}.yaml:")
    print(f"        model.path: models/{args.product}/v{version}/bank.pt")
    print(f"        decision.threshold: {threshold:.4f}")


if __name__ == "__main__":
    main()
