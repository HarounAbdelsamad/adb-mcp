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
        import os

        # Skip slow model-host connectivity checks on first init.
        os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
        from paddleocr import PaddleOCR  # type: ignore

        _paddle_engine = PaddleOCR(
            lang="en",
            use_doc_orientation_classify=False,
            use_doc_unwarping=False,
            use_textline_orientation=False,
            enable_mkldnn=False,  # required on Windows + PaddlePaddle 3.3.x CPU
        )
    return _paddle_engine


def _poly_to_bbox(poly) -> dict[str, int]:
    if poly is None:
        return {"x": 0, "y": 0, "w": 0, "h": 0}
    try:
        if len(poly) == 0:
            return {"x": 0, "y": 0, "w": 0, "h": 0}
    except TypeError:
        return {"x": 0, "y": 0, "w": 0, "h": 0}
    xs = [float(p[0]) for p in poly]
    ys = [float(p[1]) for p in poly]
    x, y = int(min(xs)), int(min(ys))
    return {"x": x, "y": y, "w": int(max(xs) - min(xs)), "h": int(max(ys) - min(ys))}


def _page_to_dict(page) -> dict:
    if isinstance(page, dict):
        return page
    if hasattr(page, "json"):
        data = page.json
        if isinstance(data, dict):
            return data
    return getattr(page, "__dict__", {})


def _parse_paddle_results(results) -> list[dict]:
    """Normalize PaddleOCR 2.x and 3.x result shapes into OCR spans."""
    spans: list[dict] = []
    if not results:
        return spans

    # PaddleOCR 3.x: list of dict-like page results from predict().
    for page in results:
        data = _page_to_dict(page)
        texts = data.get("rec_texts") or data.get("rec_text") or []
        scores = data.get("rec_scores") or data.get("rec_score") or []
        polys = data.get("rec_polys") or data.get("dt_polys") or data.get("dt_polygons") or []
        if texts:
            for i, text in enumerate(texts):
                text = str(text).strip()
                if not text:
                    continue
                conf = float(scores[i]) if i < len(scores) else 0.0
                bbox = _poly_to_bbox(polys[i] if i < len(polys) else [])
                spans.append({"text": text, "bbox": bbox, "conf": round(conf, 3)})
            continue

        # Some builds expose a single "res" payload.
        res = data.get("res")
        if isinstance(res, dict):
            texts = res.get("rec_texts") or []
            scores = res.get("rec_scores") or []
            polys = res.get("dt_polys") or []
            for i, text in enumerate(texts):
                text = str(text).strip()
                if not text:
                    continue
                conf = float(scores[i]) if i < len(scores) else 0.0
                bbox = _poly_to_bbox(polys[i] if i < len(polys) else [])
                spans.append({"text": text, "bbox": bbox, "conf": round(conf, 3)})

    if spans:
        return spans

    # PaddleOCR 2.x: [[ [box,(text,conf)], ... ]]
    lines = results[0] if results and isinstance(results[0], list) else results
    for line in lines or []:
        if not line or len(line) < 2:
            continue
        box_pts, rec = line[0], line[1]
        text = rec[0] if isinstance(rec, (list, tuple)) else str(rec)
        conf = float(rec[1]) if isinstance(rec, (list, tuple)) and len(rec) > 1 else 0.0
        spans.append({"text": str(text), "bbox": _poly_to_bbox(box_pts), "conf": round(conf, 3)})
    return spans


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
        import numpy as np

        engine = _get_paddle()
        results = engine.predict(np.array(image))
        return _parse_paddle_results(results)
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
