"""Load and manage per-product configuration files (configs/products/<id>.yaml)."""
from __future__ import annotations
import yaml
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[2]
CONFIG_DIR = PROJECT_ROOT / "configs" / "products"


def load_product_config(product_id: str) -> dict:
    path = CONFIG_DIR / f"{product_id}.yaml"
    if not path.exists():
        raise FileNotFoundError(
            f"No config file found for product '{product_id}'. "
            f"Copy {CONFIG_DIR / '_template.yaml'} to {path} and fill it in."
        )
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)


def list_products() -> list[str]:
    """List every product_id that has a config file (skips _template.yaml)."""
    return sorted(
        p.stem for p in CONFIG_DIR.glob("*.yaml") if not p.stem.startswith("_")
    )


def resolve_path(relative: str) -> Path:
    """Every path in a config file is written relative to the project root."""
    return PROJECT_ROOT / relative
