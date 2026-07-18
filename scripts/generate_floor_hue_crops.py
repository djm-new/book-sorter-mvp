#!/usr/bin/env python3
"""Generate tight book crops from the bundled floor photos using floor-hue segmentation.

This is intentionally deterministic so the static review app can use generated crop
assets instead of brittle hand boxes.
"""
from __future__ import annotations

import json
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
SRC_DIR = ROOT / "sample-images"
OUT_DIR = ROOT / "sample-crops"
MANIFEST = OUT_DIR / "manifest.json"

FLOOR_LOW = np.array([6, 38, 35], dtype=np.uint8)
FLOOR_HIGH = np.array([29, 178, 208], dtype=np.uint8)
MIN_AREA_FRAC = 0.0035
MAX_AREA_FRAC = 0.70
FILL_MIN = 0.35
SPLIT_VALLEY_FRAC = 0.16
PAD = 8


def floor_inverse_mask(bgr: np.ndarray) -> np.ndarray:
    hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
    floor = cv2.inRange(hsv, FLOOR_LOW, FLOOR_HIGH)
    book = cv2.bitwise_not(floor)
    # Clear extreme border noise outside the photographed layout.
    k = max(3, round(min(bgr.shape[:2]) * 0.005))
    if k % 2 == 0:
        k += 1
    kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (k, k))
    book = cv2.morphologyEx(book, cv2.MORPH_OPEN, kernel, iterations=2)
    book = cv2.morphologyEx(book, cv2.MORPH_CLOSE, kernel, iterations=3)
    return book


def component_boxes(mask: np.ndarray) -> list[tuple[int, int, int, int]]:
    h, w = mask.shape
    n, labels, stats, _ = cv2.connectedComponentsWithStats(mask, 8)
    boxes = []
    for i in range(1, n):
        x, y, bw, bh, area = stats[i]
        if area < h * w * MIN_AREA_FRAC or area > h * w * MAX_AREA_FRAC:
            continue
        if bw > w * 0.96 and bh > h * 0.96:
            continue
        boxes.append((int(x), int(y), int(x + bw), int(y + bh)))
    return boxes


def tight_box(mask: np.ndarray, box: tuple[int, int, int, int]) -> tuple[int, int, int, int] | None:
    x1, y1, x2, y2 = box
    roi = mask[y1:y2, x1:x2]
    pts = cv2.findNonZero(roi)
    if pts is None:
        return None
    x, y, w, h = cv2.boundingRect(pts)
    H, W = mask.shape
    return (
        max(0, x1 + x - PAD),
        max(0, y1 + y - PAD),
        min(W, x1 + x + w + PAD),
        min(H, y1 + y + h + PAD),
    )


def fill_ratio(mask: np.ndarray, box: tuple[int, int, int, int]) -> float:
    x1, y1, x2, y2 = box
    area = max(1, (x2 - x1) * (y2 - y1))
    return float(np.count_nonzero(mask[y1:y2, x1:x2])) / area


def audit_floor_like(bgr: np.ndarray, mask: np.ndarray, box: tuple[int, int, int, int]) -> bool:
    x1, y1, x2, y2 = box
    crop = bgr[y1:y2, x1:x2]
    if crop.size == 0:
        return True
    gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    edges = cv2.Canny(gray, 60, 160)
    edge_density = 100.0 * float(np.count_nonzero(edges)) / max(1, edges.size)
    hsv = cv2.cvtColor(crop, cv2.COLOR_BGR2HSV)
    sat = hsv[:, :, 1]
    saturated = sat > 45
    hue_std = float(np.std(hsv[:, :, 0][saturated])) if np.any(saturated) else 0.0
    mean_sat = float(np.mean(sat))
    fill = fill_ratio(mask, box)
    return fill < FILL_MIN or (edge_density < 6 and hue_std < 25 and mean_sat < 70)


def valley_split(mask: np.ndarray, box: tuple[int, int, int, int]) -> list[tuple[int, int, int, int]]:
    x1, y1, x2, y2 = box
    w, h = x2 - x1, y2 - y1
    if w <= 0 or h <= 0:
        return []
    # Recurse after tightening first; components that are extremely wide/tall are usually merged books.
    ratio = w / max(1, h)
    if ratio > 1.65 and w > 150:
        roi = mask[y1:y2, x1:x2] > 0
        col = roi.sum(axis=0)
        lo, hi = int(w * 0.28), int(w * 0.72)
        if hi > lo:
            rel = int(np.argmin(col[lo:hi]))
            cut = lo + rel
            if col[cut] < h * SPLIT_VALLEY_FRAC:
                return split_recursive(mask, (x1, y1, x1 + cut, y2)) + split_recursive(mask, (x1 + cut, y1, x2, y2))
    if ratio < 0.60 and h > 150:
        roi = mask[y1:y2, x1:x2] > 0
        row = roi.sum(axis=1)
        lo, hi = int(h * 0.28), int(h * 0.72)
        if hi > lo:
            rel = int(np.argmin(row[lo:hi]))
            cut = lo + rel
            if row[cut] < w * SPLIT_VALLEY_FRAC:
                return split_recursive(mask, (x1, y1, x2, y1 + cut)) + split_recursive(mask, (x1, y1 + cut, x2, y2))
    return [box]


def split_recursive(mask: np.ndarray, box: tuple[int, int, int, int], depth: int = 0) -> list[tuple[int, int, int, int]]:
    if depth > 6:
        return [box]
    tight = tight_box(mask, box)
    if tight is None:
        return []
    split = valley_split(mask, tight)
    if len(split) == 1 and split[0] == tight:
        return [tight]
    out: list[tuple[int, int, int, int]] = []
    for child in split:
        if child != box:
            out.extend(split_recursive(mask, child, depth + 1))
    return out


def dedupe(boxes: list[tuple[int, int, int, int]]) -> list[tuple[int, int, int, int]]:
    def area(b):
        return max(0, b[2] - b[0]) * max(0, b[3] - b[1])
    def iou(a, b):
        ix1, iy1 = max(a[0], b[0]), max(a[1], b[1])
        ix2, iy2 = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, ix2 - ix1) * max(0, iy2 - iy1)
        return inter / max(1, area(a) + area(b) - inter)
    kept: list[tuple[int, int, int, int]] = []
    for box in sorted(boxes, key=area, reverse=True):
        if all(iou(box, k) < 0.55 for k in kept):
            kept.append(box)
    return kept


def sort_boxes(boxes: list[tuple[int, int, int, int]], image_h: int) -> list[tuple[int, int, int, int]]:
    row_band = max(1, int(image_h * 0.055))
    return sorted(boxes, key=lambda b: (round(b[1] / row_band), b[0]))


def process_one(path: Path) -> list[dict]:
    bgr = cv2.imread(str(path))
    if bgr is None:
        raise RuntimeError(f"Could not read {path}")
    H, W = bgr.shape[:2]
    mask = floor_inverse_mask(bgr)
    raw = component_boxes(mask)
    split: list[tuple[int, int, int, int]] = []
    for box in raw:
        split.extend(split_recursive(mask, box))
    boxes = []
    for box in dedupe(split):
        tight = tight_box(mask, box)
        if not tight:
            continue
        x1, y1, x2, y2 = tight
        bw, bh = x2 - x1, y2 - y1
        if bw < W * 0.06 or bh < H * 0.055:
            continue
        if audit_floor_like(bgr, mask, tight):
            continue
        boxes.append(tight)
    boxes = sort_boxes(boxes, H)

    sample_name = path.stem
    sample_out = OUT_DIR / sample_name
    sample_out.mkdir(parents=True, exist_ok=True)
    for old in sample_out.glob("*.jpg"):
        old.unlink()
    items = []
    for idx, (x1, y1, x2, y2) in enumerate(boxes, 1):
        crop = bgr[y1:y2, x1:x2]
        out_name = f"{idx:02d}.jpg"
        out_path = sample_out / out_name
        cv2.imwrite(str(out_path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 92])
        roi = mask[y1:y2, x1:x2]
        items.append({
            "id": f"{sample_name}-{idx:02d}",
            "title": f"Photo {int(sample_name)} book {idx:02d}",
            "src": f"/sample-crops/{sample_name}/{out_name}",
            "source": f"sample-{sample_name}.jpg",
            "box": [int(x1), int(y1), int(x2 - x1), int(y2 - y1)],
            "fill": round(float(np.count_nonzero(roi)) / max(1, roi.size), 3),
            "aspectRatio": round((x2 - x1) / max(1, (y2 - y1)), 4),
            "rotation": 0,
        })
    return items


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    manifest = {"generatedBy": "floor-hue-segmentation-v1", "items": []}
    for src in sorted(SRC_DIR.glob("*.jpg")):
        items = process_one(src)
        print(src.name, len(items))
        manifest["items"].extend(items)
    MANIFEST.write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print("total", len(manifest["items"]), "->", MANIFEST)


if __name__ == "__main__":
    main()
