"""Khoanh vùng nghi ngờ/lỗi lên ảnh gốc, để người kiểm tra thấy ngay AI đang
nghi ngờ ở đâu — không chỉ có điểm số."""
from __future__ import annotations
from PIL import Image, ImageDraw


def draw_defect_box(image: Image.Image, heatmap: list[list[float]] | None, grid: int,
                     threshold: float, color=(224, 60, 50), width: int = 4) -> Image.Image:
    """Khung đỏ đậm = vùng lệch nhiều nhất (nguyên nhân chính bị đánh giá NG).
    Khung vàng mảnh = vùng khác cũng vượt ngưỡng nhưng không phải nặng nhất."""
    if not heatmap:
        return image.convert("RGB")
    annotated = image.convert("RGB").copy()
    w, h = annotated.size
    pw, ph = w / grid, h / grid
    draw = ImageDraw.Draw(annotated)

    flat = [(r, c, heatmap[r][c]) for r in range(grid) for c in range(grid)]
    worst_r, worst_c, _ = max(flat, key=lambda t: t[2])

    for r, c, score in flat:
        if score <= threshold or (r, c) == (worst_r, worst_c):
            continue
        box = (c * pw, r * ph, (c + 1) * pw, (r + 1) * ph)
        draw.rectangle(box, outline=(219, 161, 60), width=max(2, width // 2))

    box = (worst_c * pw, worst_r * ph, (worst_c + 1) * pw, (worst_r + 1) * ph)
    draw.rectangle(box, outline=color, width=width)
    return annotated
