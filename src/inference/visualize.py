"""Draw the suspected/defective region onto the original image, so the
inspector can see at a glance where the AI is suspicious — not just a score."""
from __future__ import annotations
from PIL import Image, ImageDraw


def draw_defect_box(image: Image.Image, heatmap: list[list[float]] | None, grid: int,
                     threshold: float, color=(224, 60, 50), width: int = 4) -> Image.Image:
    """Solid red box = the single worst-matching region (main reason for the
    NG verdict). Thin yellow box = another region also over threshold, but
    not the worst one."""
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
