"""Export face-aware thumbnail candidate JPEGs by seeking to peak timestamps."""

from __future__ import annotations

from pathlib import Path


def _nearest_box(face_boxes: list[dict], t: float, window: float = 2.5) -> "dict | None":
    best = None
    best_d = window
    for b in face_boxes:
        d = abs(float(b.get("t", 0.0)) - t)
        if d <= best_d:
            best_d = d
            best = b
    return best


def _crop_to_aspect(frame, target_ar: float, cx: float, cy: float):
    h, w = frame.shape[:2]
    cur_ar = w / max(1, h)
    if cur_ar > target_ar:
        new_w = int(round(h * target_ar))
        new_h = h
    else:
        new_w = w
        new_h = int(round(w / target_ar))
    new_w = max(1, min(new_w, w))
    new_h = max(1, min(new_h, h))
    ccx = int(cx * w)
    ccy = int(cy * h)
    x0 = min(max(0, ccx - new_w // 2), w - new_w)
    y0 = min(max(0, ccy - new_h // 2), h - new_h)
    return frame[y0 : y0 + new_h, x0 : x0 + new_w]


def export_thumbnails(
    video_path,
    timestamps: list[float],
    face_boxes: list[dict],
    out_dir,
    base: str = "thumb",
    size: tuple[int, int] = (1280, 720),
    max_count: int = 6,
) -> list[dict]:
    """Write up to ``max_count`` JPEGs cropped 16:9 around the subject.

    Returns ``[{t, path}]``. Never raises — decode/seek issues yield fewer (or
    zero) thumbnails so the pipeline degrades gracefully.
    """
    if not timestamps:
        return []
    try:
        import cv2
    except Exception:
        return []

    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        return []

    results: list[dict] = []
    target_ar = size[0] / size[1]
    try:
        for i, t in enumerate(timestamps[:max_count]):
            try:
                cap.set(cv2.CAP_PROP_POS_MSEC, float(t) * 1000.0)
                ok, frame = cap.read()
                if not ok or frame is None:
                    continue
                cx, cy = 0.5, 0.42
                box = _nearest_box(face_boxes, float(t))
                if box:
                    cx = float(box.get("cx", cx))
                    cy = float(box.get("cy", cy))
                crop = _crop_to_aspect(frame, target_ar, cx, cy)
                crop = cv2.resize(crop, size, interpolation=cv2.INTER_AREA)
                path = out_dir / f"{base}_{i + 1}.jpg"
                if cv2.imwrite(str(path), crop, [int(cv2.IMWRITE_JPEG_QUALITY), 90]):
                    results.append({"t": round(float(t), 2), "path": str(path)})
            except Exception:
                continue
    finally:
        cap.release()
    return results
