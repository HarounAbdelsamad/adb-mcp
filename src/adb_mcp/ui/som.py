from __future__ import annotations

import base64
import io

from PIL import Image, ImageDraw, ImageFont

# 8-colour high-contrast palette (works on light AND dark UIs)
_PALETTE = [
    (255, 59, 48),    # red
    (255, 149, 0),    # orange
    (255, 204, 0),    # yellow
    (52, 199, 89),    # green
    (0, 199, 190),    # teal
    (0, 122, 255),    # blue
    (175, 82, 222),   # purple
    (255, 45, 85),    # pink
]


def _get_font(size: int = 14) -> ImageFont.ImageFont:
    try:
        return ImageFont.truetype("arial.ttf", size)
    except Exception:
        return ImageFont.load_default()


def annotate(image: Image.Image, nodes: list, scale: float = 1.0) -> Image.Image:
    """Draw numbered SoM badges on *image* and return a new annotated copy."""
    out = image.copy().convert("RGBA")
    overlay = Image.new("RGBA", out.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    font = _get_font(14)

    for node in nodes:
        b = node.bounds
        x1 = int(b["x"] * scale)
        y1 = int(b["y"] * scale)
        x2 = int((b["x"] + b["w"]) * scale)
        y2 = int((b["y"] + b["h"]) * scale)

        color = _PALETTE[node.id % len(_PALETTE)]
        color_a = color + (180,)
        outline_a = color + (255,)

        # Bounds outline
        draw.rectangle([x1, y1, x2, y2], outline=outline_a, width=2)

        # Badge background
        label = str(node.id)
        bbox = draw.textbbox((0, 0), label, font=font)
        bw = bbox[2] - bbox[0] + 6
        bh = bbox[3] - bbox[1] + 4
        bx, by = x1, max(0, y1 - bh)
        draw.rounded_rectangle([bx, by, bx + bw, by + bh], radius=3, fill=color_a, outline=(0, 0, 0, 200), width=1)

        # Label text
        draw.text((bx + 3, by + 2), label, fill=(255, 255, 255, 255), font=font)

    result = Image.alpha_composite(out, overlay).convert("RGB")
    return result


def annotate_to_base64(image: Image.Image, nodes: list, scale: float = 1.0) -> str:
    annotated = annotate(image, nodes, scale)
    buf = io.BytesIO()
    annotated.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
