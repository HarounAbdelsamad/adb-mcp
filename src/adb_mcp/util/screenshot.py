from __future__ import annotations

import base64
import io

import uiautomator2 as u2
from PIL import Image

from ..config import cfg


def capture(d: u2.Device) -> Image.Image:
    """Take a screenshot from the device and return a PIL Image."""
    return d.screenshot()


def downscale(image: Image.Image, max_dim: int | None = None) -> Image.Image:
    limit = max_dim or cfg.screenshot_max_dim
    w, h = image.size
    if w <= limit and h <= limit:
        return image
    ratio = limit / max(w, h)
    new_w, new_h = int(w * ratio), int(h * ratio)
    return image.resize((new_w, new_h), Image.LANCZOS)


def to_base64_png(image: Image.Image) -> str:
    buf = io.BytesIO()
    image.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()
