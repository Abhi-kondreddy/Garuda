from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

import cv2
import numpy as np


def _rgb_to_hex(r: int, g: int, b: int) -> str:
    return f"#{r:02x}{g:02x}{b:02x}"


def _quantize_color(bgr: np.ndarray) -> tuple[int, int, int]:
    # OpenCV BGR -> quantized RGB for palette
    b, g, r = [int(x) for x in bgr]
    step = 32
    return ((r // step) * step, (g // step) * step, (b // step) * step)


def analyze_frames(
    *,
    video_path: Path,
    duration: float,
    fps: float,
    on_progress: Callable[[float, str], None],
    sample_every: int | None = None,
) -> dict:
    cap = cv2.VideoCapture(str(video_path))
    if not cap.isOpened():
        raise RuntimeError(f"Could not open video: {video_path}")

    total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT) or 0)
    if total <= 0 and duration > 0 and fps > 0:
        total = int(duration * fps)

    width = int(cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)

    brightness: list[float] = []
    contrast: list[float] = []
    motion: list[float] = []
    hue_means: list[float] = []
    sat_means: list[float] = []
    times: list[float] = []
    scene_cuts: list[float] = []
    palette_counter: Counter[tuple[int, int, int]] = Counter()

    prev_gray = None
    prev_hist = None
    frame_idx = 0
    # Default: every frame (Report analyzer). Editor may pass a stride for 4K/long clips.
    if sample_every is None or sample_every < 1:
        sample_every = 1

    face_cascade = cv2.CascadeClassifier(
        cv2.data.haarcascades + "haarcascade_frontalface_default.xml"
    )
    face_hits = 0
    face_checks = 0
    # Dense face sampling ~3 fps equivalent
    face_stride = max(1, int(round(fps / 3.0))) if fps > 0 else 10

    on_progress(
        1,
        f"Visual analysis · decoding frames… (sample every {sample_every}"
        + (f", {width}px" if width else "")
        + ")",
    )

    while True:
        ok, frame = cap.read()
        if not ok:
            break

        t = frame_idx / fps if fps > 0 else frame_idx / 30.0
        if frame_idx % sample_every == 0:
            small = cv2.resize(frame, (160, 90), interpolation=cv2.INTER_AREA)
            gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
            hsv = cv2.cvtColor(small, cv2.COLOR_BGR2HSV)

            bri = float(np.mean(gray))
            con = float(np.std(gray))
            brightness.append(bri)
            contrast.append(con)
            hue_means.append(float(np.mean(hsv[:, :, 0])))
            sat_means.append(float(np.mean(hsv[:, :, 1])))
            times.append(t)

            # palette sample from center crop
            cy, cx = small.shape[0] // 2, small.shape[1] // 2
            patch = small[max(0, cy - 8) : cy + 8, max(0, cx - 8) : cx + 8]
            mean_bgr = np.mean(patch.reshape(-1, 3), axis=0)
            palette_counter[_quantize_color(mean_bgr)] += 1

            hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
            hist = cv2.normalize(hist, hist).flatten()
            if prev_hist is not None:
                diff = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                if diff > 0.45:
                    scene_cuts.append(t)
            prev_hist = hist

            if prev_gray is not None:
                delta = cv2.absdiff(gray, prev_gray)
                motion.append(float(np.mean(delta)))
            else:
                motion.append(0.0)
            prev_gray = gray

        if frame_idx % face_stride == 0:
            face_checks += 1
            # use medium resolution for faces
            mid = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
            g = cv2.cvtColor(mid, cv2.COLOR_BGR2GRAY)
            faces = face_cascade.detectMultiScale(g, scaleFactor=1.15, minNeighbors=4, minSize=(24, 24))
            if len(faces) > 0:
                face_hits += 1

        frame_idx += 1
        # Throttle progress (~2% steps) so Electron IPC stays responsive
        step = max(1, total // 50) if total > 0 else 30
        if total > 0 and frame_idx % step == 0:
            pct = min(99, 100.0 * frame_idx / total)
            on_progress(
                pct,
                f"Visual analysis · frames {frame_idx}/{total} · on-cam {face_hits}/{max(face_checks, 1)}",
            )

    cap.release()
    on_progress(
        100,
        f"Visual analysis complete · {frame_idx} frames · on-cam {face_hits}/{max(face_checks, 1)}",
    )
    # Build per-second aggregates for timeline
    if not times:
        return {
            "frame_count": frame_idx,
            "brightness": [],
            "contrast": [],
            "motion": [],
            "times": [],
            "scene_cuts": [],
            "palette": [],
            "on_cam_presence": 0.0,
            "hue_means": [],
            "sat_means": [],
            "timeline_bins": [],
        }

    bin_size = 0.5
    n_bins = max(1, int(np.ceil(max(times) / bin_size)) + 1)
    bins = [
        {"t": i * bin_size, "motion": [], "brightness": [], "contrast": []}
        for i in range(n_bins)
    ]
    for i, t in enumerate(times):
        bi = min(n_bins - 1, int(t / bin_size))
        bins[bi]["motion"].append(motion[i])
        bins[bi]["brightness"].append(brightness[i])
        bins[bi]["contrast"].append(contrast[i])

    timeline_bins = []
    for b in bins:
        if not b["motion"]:
            continue
        timeline_bins.append(
            {
                "t": b["t"],
                "motion": float(np.mean(b["motion"])),
                "brightness": float(np.mean(b["brightness"])),
                "contrast": float(np.mean(b["contrast"])),
            }
        )

    total_w = sum(palette_counter.values()) or 1
    palette = [
        {"hex": _rgb_to_hex(*rgb), "weight": count / total_w}
        for rgb, count in palette_counter.most_common(6)
    ]

    return {
        "frame_count": frame_idx,
        "brightness": brightness,
        "contrast": contrast,
        "motion": motion,
        "times": times,
        "scene_cuts": scene_cuts,
        "palette": palette,
        "on_cam_presence": face_hits / max(face_checks, 1),
        "hue_means": hue_means,
        "sat_means": sat_means,
        "timeline_bins": timeline_bins,
        "fps": fps,
        "duration": duration,
    }
