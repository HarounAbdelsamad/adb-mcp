from __future__ import annotations

import difflib
import logging

from PIL import Image

from ..config import cfg

log = logging.getLogger(__name__)

_paddle_engine: object | None = None


def _get_paddle():
    global _paddle_engine
    if _paddle_engine is None:
        from paddleocr import PaddleOCR  # type: ignore
        _paddle_engine = PaddleOCR(lang="en", use_angle_cls=False, show_log=False)
    return _paddle_engine


def _iou(b1: dict, b2: dict) -> float:
    """Intersection-over-union of two {x,y,w,h} boxes."""
    x1a, y1a = b1["x"], b1["y"]
    x2a, y2a = x1a + b1["w"], y1a + b1["h"]
    x1b, y1b = b2["x"], b2["y"]
    x2b, y2b = x1b + b2["w"], y1b + b2["h"]

    ix1, iy1 = max(x1a, x1b), max(y1a, y1b)
    ix2, iy2 = min(x2a, x2b), min(y2a, y2b)
    iw, ih = max(0, ix2 - ix1), max(0, iy2 - iy1)
    inter = iw * ih
    if inter == 0:
        return 0.0
    union = b1["w"] * b1["h"] + b2["w"] * b2["h"] - inter
    return inter / union if union else 0.0


def run_ocr(image: Image.Image) -> list[dict]:
    """Return list of {text, bbox:{x,y,w,h}, conf} spans."""
    if cfg.ocr_engine == "none" or not cfg.ocr_enabled:
        return []

    if cfg.ocr_engine == "tesseract":
        return _run_tesseract(image)

    return _run_paddle(image)


def _run_paddle(image: Image.Image) -> list[dict]:
    try:
        engine = _get_paddle()
        results = engine.ocr(image, cls=False)
        spans: list[dict] = []
        if not results or not results[0]:
            return spans
        for line in results[0]:
            box_pts, (text, conf) = line
            xs = [p[0] for p in box_pts]
            ys = [p[1] for p in box_pts]
            x, y = int(min(xs)), int(min(ys))
            w, h = int(max(xs) - min(xs)), int(max(ys) - min(ys))
            spans.append({"text": text, "bbox": {"x": x, "y": y, "w": w, "h": h}, "conf": round(float(conf), 3)})
        return spans
    except Exception:
        log.exception("PaddleOCR failed")
        return []


def _run_tesseract(image: Image.Image) -> list[dict]:
    try:
        import pytesseract  # type: ignore
        data = pytesseract.image_to_data(image, output_type=pytesseract.Output.DICT)
        spans: list[dict] = []
        for i, text in enumerate(data["text"]):
            text = text.strip()
            if not text:
                continue
            conf = float(data["conf"][i])
            if conf < 0:
                continue
            x, y = int(data["left"][i]), int(data["top"][i])
            w, h = int(data["width"][i]), int(data["height"][i])
            spans.append({"text": text, "bbox": {"x": x, "y": y, "w": w, "h": h}, "conf": round(conf / 100, 3)})
        return spans
    except Exception:
        log.exception("Tesseract OCR failed")
        return []


def merge_with_tree(ocr_spans: list[dict], nodes: list) -> list[dict]:
    """
    For each OCR span, if it overlaps well with a tree node and text matches,
    mark the node as ocr_confirmed and drop the span.
    Return remaining standalone spans (canvas text, WebView, etc.).
    """
    remaining: list[dict] = []
    node_matched = set()

    for span in ocr_spans:
        best_node = None
        best_iou = 0.0
        for node in nodes:
            iou = _iou(span["bbox"], node.bounds)
            if iou > best_iou:
                best_iou = iou
                best_node = node

        if best_node and best_iou > 0.4:
            sim = difflib.SequenceMatcher(
                None, span["text"].lower(), (best_node.text or best_node.content_desc or "").lower()
            ).ratio()
            if sim > 0.65:
                node_matched.add(best_node.id)
                # Enrich node text if tree text was empty
                if not best_node.text and span["text"]:
                    best_node.text = span["text"]
                continue
        remaining.append(span)

    return remaining
