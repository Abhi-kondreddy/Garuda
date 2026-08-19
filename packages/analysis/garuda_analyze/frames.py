from __future__ import annotations

from collections import Counter
from pathlib import Path
from typing import Callable

import cv2
import numpy as np

from . import config
from .detectors import FaceDetector
from .performance import yield_frame_tick


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
    sharpness: list[float] = []
    rgb_means: list[list[float]] = []
    shadow_clip: list[float] = []
    highlight_clip: list[float] = []
    times: list[float] = []
    scene_cuts: list[float] = []
    palette_counter: Counter[tuple[int, int, int]] = Counter()

    prev_gray = None
    prev_hist = None
    frame_idx = 0
    cut_threshold = config.SCENE_CUT_BHATTACHARYYA
    # Default: every frame (Report analyzer). Editor may pass a stride for 4K/long clips.
    if sample_every is None or sample_every < 1:
        sample_every = 1

    # YuNet DNN when the model is bundled, else Haar; a missing detector simply
    # disables the face pass instead of crashing all visual analysis.
    detector = FaceDetector()
    face_enabled = detector.available
    face_hits = 0
    face_checks = 0
    face_boxes: list[dict] = []
    face_area_ratios: list[float] = []
    face_center_offsets: list[float] = []
    face_center_xs: list[float] = []
    # Dense face sampling ~3 fps equivalent
    face_stride = max(1, int(round(fps / 3.0))) if fps > 0 else 10

    on_progress(
        1,
        f"Visual analysis · decoding frames… (sample every {sample_every}"
        + (f", {width}px" if width else "")
        + ")",
    )

    try:
        while True:
            # grab() advances the decoder cheaply; only retrieve()/decode the
            # frames we actually sample or face-check. For sample_every == 1
            # (report path) this is every frame, same as before; for the
            # editor's strided path it skips decoding frames we'd discard.
            if not cap.grab():
                break

            need_sample = frame_idx % sample_every == 0
            need_face = face_enabled and (frame_idx % face_stride == 0)

            if need_sample or need_face:
                ok, frame = cap.retrieve()
                # Some codecs return ok=True with a None frame at EOF/corruption.
                if not ok or frame is None:
                    break
                t = frame_idx / fps if fps > 0 else frame_idx / 30.0

                if need_sample:
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

                    # Cheap per-sample signals for the vision metric plugins.
                    sharpness.append(float(cv2.Laplacian(gray, cv2.CV_64F).var()))
                    rgb_means.append(
                        [float(np.mean(small[:, :, 2])), float(np.mean(small[:, :, 1])), float(np.mean(small[:, :, 0]))]
                    )
                    shadow_clip.append(float(np.mean(gray < 16)))
                    highlight_clip.append(float(np.mean(gray > 239)))

                    # palette sample from center crop
                    cy, cx = small.shape[0] // 2, small.shape[1] // 2
                    patch = small[max(0, cy - 8) : cy + 8, max(0, cx - 8) : cx + 8]
                    mean_bgr = np.mean(patch.reshape(-1, 3), axis=0)
                    palette_counter[_quantize_color(mean_bgr)] += 1

                    hist = cv2.calcHist([gray], [0], None, [32], [0, 256])
                    hist = cv2.normalize(hist, hist).flatten()
                    if prev_hist is not None:
                        diff = float(cv2.compareHist(prev_hist, hist, cv2.HISTCMP_BHATTACHARYYA))
                        if diff > cut_threshold:
                            scene_cuts.append(t)
                    prev_hist = hist

                    if prev_gray is not None:
                        delta = cv2.absdiff(gray, prev_gray)
                        # Normalize by stride so motion is comparable across
                        # sampling rates (a bigger frame gap = bigger raw delta).
                        motion.append(float(np.mean(delta)) / float(sample_every))
                    else:
                        motion.append(0.0)
                    prev_gray = gray

                if need_face:
                    face_checks += 1
                    # use medium resolution for faces
                    mid = cv2.resize(frame, (320, 180), interpolation=cv2.INTER_AREA)
                    faces = detector.detect(mid)
                    if faces:
                        face_hits += 1
                        # Largest face -> normalized center + size (0..1) for
                        # thumbnail crops / vertical reframing downstream.
                        fx, fy, fw, fh = max(faces, key=lambda b: b[2] * b[3])
                        cxn = (fx + fw / 2.0) / 320.0
                        face_boxes.append(
                            {
                                "t": round(t, 2),
                                "cx": round(cxn, 4),
                                "cy": round((fy + fh / 2.0) / 180.0, 4),
                                "w": round(fw / 320.0, 4),
                                "h": round(fh / 180.0, 4),
                            }
                        )
                        # Framing / vertical-crop aggregates (from resource-monitoring branch).
                        face_area_ratios.append((float(fw) * float(fh)) / (320.0 * 180.0))
                        face_center_offsets.append(abs(cxn - 0.5))
                        face_center_xs.append(cxn)

            frame_idx += 1
            yield_frame_tick()
            # Throttle progress (~2% steps) so Electron IPC stays responsive
            step = max(1, total // 50) if total > 0 else 30
            if total > 0 and frame_idx % step == 0:
                pct = min(99, 100.0 * frame_idx / total)
                on_progress(
                    pct,
                    f"Visual analysis · frames {frame_idx}/{total} · on-cam {face_hits}/{max(face_checks, 1)}",
                )
    finally:
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
            "face_avg_area_ratio": 0.0,
            "face_center_offset": 0.5,
            "face_center_x": 0.5,
            "vertical_crop_safe": 50.0,
            "hue_means": [],
            "sat_means": [],
            "sharpness": [],
            "rgb_means": [],
            "shadow_clip": [],
            "highlight_clip": [],
            "timeline_bins": [],
            "face_boxes": [],
            "face_backend": detector.backend,
        }

    bin_size = config.TIMELINE_BIN_SEC
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

    on_cam = face_hits / max(face_checks, 1)
    face_avg_area = float(np.mean(face_area_ratios)) if face_area_ratios else 0.0
    face_center = float(np.mean(face_center_offsets)) if face_center_offsets else 0.5
    face_center_x = float(np.mean(face_center_xs)) if face_center_xs else 0.5
    # 9:16 crop safety: centered face + reasonable size
    vertical_crop_safe = float(
        max(
            0.0,
            min(
                100.0,
                55.0
                + 30.0 * (1.0 - min(1.0, face_center * 2.0))
                + 15.0 * min(1.0, face_avg_area * 8.0)
                + 10.0 * on_cam,
            ),
        )
    )

    return {
        "frame_count": frame_idx,
        "brightness": brightness,
        "contrast": contrast,
        "motion": motion,
        "times": times,
        "scene_cuts": scene_cuts,
        "palette": palette,
        "on_cam_presence": on_cam,
        "face_avg_area_ratio": round(face_avg_area, 4),
        "face_center_offset": round(face_center, 4),
        "face_center_x": round(face_center_x, 4),
        "vertical_crop_safe": round(vertical_crop_safe, 1),
        "hue_means": hue_means,
        "sat_means": sat_means,
        "sharpness": sharpness,
        "rgb_means": rgb_means,
        "shadow_clip": shadow_clip,
        "highlight_clip": highlight_clip,
        "timeline_bins": timeline_bins,
        "face_boxes": face_boxes,
        "face_backend": detector.backend,
        "fps": fps,
        "duration": duration,
    }
