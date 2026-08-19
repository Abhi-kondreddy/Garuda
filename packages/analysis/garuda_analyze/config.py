"""Central tunables for the Garuda scoring heuristics.

Every weight/threshold/magic-number used by the scoring layer lives here so the
model is inspectable, testable, and versionable. Bump ``SCORING_VERSION`` when a
change makes scores non-comparable to previously generated reports.
"""

from __future__ import annotations

# Heuristic model version stamped into every report (distinct from the report
# schema ``version``). Surface it in the UI so old/new scores aren't compared.
SCORING_VERSION = "2026.08-heur1"

# --- timeline / interestingness ---
# Motion value that maps to a full-scale (100) motion score.
MOTION_FULL_SCALE = 25.0
# Component scores are 0..100 so the weighted sum can actually reach 100
# (previously speech maxed at 80 and cut at 25, capping interestingness ~88.5).
SPEECH_PRESENT_SCORE = 100.0
CUT_BOOST_SCORE = 100.0
SPEECH_PAD_SEC = 0.25
CUT_PROXIMITY_SEC = 0.35
INTEREST_WEIGHTS = {"motion": 0.4, "audio": 0.3, "speech": 0.2, "cut": 0.1}

# --- visual consistency ---
BRIGHTNESS_STD_PENALTY = 1.2
CONTRAST_STD_PENALTY = 1.5
HUE_STD_PENALTY = 1.8
SAT_STD_PENALTY = 0.35
EXPOSURE_FLICKER_GAIN = 1.4
STATIC_MOTION_FLOOR = 1.5
STATIC_MOTION_PERCENTILE = 25
# Color is scored/weighted separately in `overall`, so it is intentionally NOT
# part of visual_quality (avoids double-counting color evenness).
VISUAL_QUALITY_WEIGHTS = {"brightness": 0.40, "contrast": 0.30, "static": 0.30}

# --- hook ---
HOOK_WEIGHTS = {
    "motion": 0.30,
    "audio": 0.25,
    "speech_onset": 0.20,
    "early_cuts": 0.15,
    "on_cam": 0.10,
}

# --- audio quality ---
AUDIO_QUALITY_WEIGHTS = {"clarity": 0.35, "loudness": 0.35, "dead": 0.20, "clip": 0.10}
CLIP_PENALTY_SCALE = 20.0

# --- overall ---
OVERALL_WEIGHTS = {
    "hook": 0.22,
    "interest": 0.28,
    "color": 0.15,
    "visual": 0.15,
    "audio": 0.20,
}

# --- risk zones ---
RISK_LOW_THRESHOLD = 35.0
RISK_MIN_STRETCH_SEC = 4.0
RISK_HIGH_STRETCH_SEC = 10.0

# --- highlights ---
HIGHLIGHT_MIN_GAP_SEC = 3.0
HIGHLIGHT_MAX = 6

# --- visual decode (frames.py) ---
SCENE_CUT_BHATTACHARYYA = 0.45
TIMELINE_BIN_SEC = 0.5
# Only run the (second-pass) PySceneDetect content detector up to this duration
# to avoid doubling decode cost on long videos; longer clips use histogram cuts.
SCENE_DETECT_MAX_SEC = 1800.0

# --- audio loading bounds (P3, cap memory on long clips) ---
AUDIO_BASE_SR = 16000
AUDIO_DOWNSAMPLE_SR = 8000
# Above this duration, load at the lower sample rate (halves memory).
AUDIO_DOWNSAMPLE_OVER_SEC = 3600.0
# Hard ceiling on analyzed audio so multi-hour files can't exhaust memory.
AUDIO_MAX_ANALYSIS_SEC = 4 * 3600.0

# --- loudness targets (P4) ---
# EBU R128 integrated-loudness targets by platform (LUFS).
LUFS_TARGETS = {"youtube": -14.0, "shorts": -14.0, "tiktok": -14.0, "instagram": -14.0}

# --- run guards (watchdog) ---
# Total wall-clock budget = base + per_min * minutes_of_video. Generous so it
# only trips on genuine hangs, not slow-but-progressing runs.
ANALYSIS_WALLCLOCK_BASE_SEC = 900.0
ANALYSIS_WALLCLOCK_PER_MIN_SEC = 120.0
# Soft peak-RSS ceiling in MB (0 disables — off by default to avoid false kills).
ANALYSIS_MEMORY_LIMIT_MB = 0.0
