"""Đọc và quản lý file cấu hình theo từng sản phẩm (configs/products/<id>.yaml)."""
from __future__ import annotations
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs" / "products"


def load_product_config(product_id: str) -> dict:
    path = CONFIG_DIR / f"{product_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"Chưa có file cấu hình cho sản phẩm '{product_id}'. "
            f"Copy {CONFIG_DIR / '_template.yaml'} thành {path} rồi điền thông số."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_products() -> list[str]:
    """Liệt kê mọi product_id đã có file cấu hình (bỏ qua _template.yaml)."""
    return sorted(
        p.stem for p in CONFIG_DIR.glob("*.yaml") if not p.stem.startswith("_")
    )


def resolve_path(relative: str) -> Path:
    """Mọi đường dẫn trong config được ghi tương đối so với thư mục gốc dự án."""
    return PROJECT_ROOT / relative
