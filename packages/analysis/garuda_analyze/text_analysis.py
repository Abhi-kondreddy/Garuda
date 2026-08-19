"""Lightweight transcript-derived outputs: YouTube chapters + keyword/SEO pack.

Dependency-free (regex + counting) so it runs anywhere the transcript exists.
"""

from __future__ import annotations

import re
from collections import Counter

from .util import fmt_timecode

# Small, high-frequency English stopword set (Telugu/other scripts pass through
# and surface as candidate keywords, which is usually what a creator wants).
_STOPWORDS = {
    "the", "and", "you", "your", "for", "are", "but", "not", "with", "this",
    "that", "have", "has", "was", "were", "will", "just", "like", "get", "got",
    "can", "cant", "dont", "its", "into", "out", "our", "they", "them", "then",
    "than", "there", "here", "what", "when", "why", "how", "who", "all", "any",
    "one", "two", "some", "more", "most", "very", "really", "gonna", "wanna",
    "okay", "yeah", "yep", "nope", "about", "because", "also", "which", "these",
    "those", "from", "over", "under", "again", "still", "even", "much", "many",
}

_WORD_RE = re.compile(r"\w{3,}", re.UNICODE)


def build_keywords(transcript: list[dict], top: int = 12) -> list[dict]:
    text = " ".join((s.get("text") or "") for s in transcript or []).lower()
    counts: Counter[str] = Counter()
    for w in _WORD_RE.findall(text):
        if w.isdigit() or w in _STOPWORDS:
            continue
        counts[w] += 1
    return [{"term": w, "count": c} for w, c in counts.most_common(top)]


def _title_at(transcript: list[dict], t: float) -> str:
    for s in transcript or []:
        if float(s.get("start") or 0.0) >= t - 0.5:
            text = (s.get("text") or "").strip()
            if text:
                return " ".join(text.split()[:7])[:60]
            break
    return "Chapter"


def build_chapters(
    transcript: list[dict],
    cuts: list[float],
    duration: float,
    max_chapters: int = 8,
) -> list[dict]:
    """Propose YouTube-style chapters. First chapter is always 0:00; boundaries
    are drawn from scene cuts spaced by a sensible minimum gap, titled from the
    nearest spoken line."""
    if duration <= 0:
        return []
    min_gap = 30.0 if duration > 300 else max(8.0, duration / 8.0)

    bounds: list[float] = [0.0]
    for c in sorted(float(x) for x in (cuts or [])):
        if c - bounds[-1] >= min_gap and c < duration - min_gap:
            bounds.append(round(c, 2))
        if len(bounds) >= max_chapters:
            break

    # Too few natural boundaries: fall back to even spacing.
    if len(bounds) < 3 and duration > min_gap * 2:
        n = min(max_chapters, max(3, int(duration // min_gap)))
        step = duration / n
        bounds = [round(i * step, 2) for i in range(n)]
        bounds[0] = 0.0

    if not transcript:
        return []  # chapters without titles aren't useful

    return [
        {"t": round(b, 2), "time": fmt_timecode(b), "title": _title_at(transcript, b)}
        for b in bounds
    ]
