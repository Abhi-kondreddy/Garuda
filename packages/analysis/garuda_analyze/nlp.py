"""Transcript NLP parameters: fillers, repetition, readability, safety, intent."""

from __future__ import annotations

import re
from collections import Counter

from .metrics import REGISTRY, Metric, unavailable
from .util import clamp

_FILLERS = re.compile(
    r"\b(um+|uh+|erm|hmm+|uhh|like|you know|i mean|actually|basically|literally|"
    r"sort of|kind of|okay so|so yeah|ante|anduke|kada|matlab|yaar)\b",
    re.I,
)
_CTA = re.compile(
    r"\b(subscribe|like the video|comment|share|follow|next video|link in|check out|"
    r"watch till|don't forget|hit the bell)\b",
    re.I,
)
_PROMISE = re.compile(
    r"\b(how to|why|secret|mistake|stop|never|always|you need|i'll show|learn|fix|"
    r"in this video|by the end)\b",
    re.I,
)
_PROFANITY = re.compile(r"\b(f\*+k|fuck|shit|bitch|asshole|bastard|dick)\b", re.I)
_RISKY_CLAIM = re.compile(
    r"\b(guaranteed|cure|miracle|get rich|100% (?:safe|working)|no risk|overnight)\b", re.I
)
_WORD = re.compile(r"[A-Za-z']+")
_VOWELS = re.compile(r"[aeiouy]+", re.I)


def _syllables(word: str) -> int:
    return max(1, len(_VOWELS.findall(word)))


@REGISTRY.register("nlp", group="language")
def _nlp(ctx: dict) -> "list[Metric]":
    transcript = ctx.get("transcript") or []
    if not transcript:
        return [unavailable("fillerRate", "Filler words", "regex", "language", "No transcript")]

    full = " ".join((s.get("text") or "") for s in transcript).strip()
    words = _WORD.findall(full)
    n_words = max(1, len(words))
    out: list[Metric] = []

    # Filler words + evidence timestamps.
    filler_hits = 0
    evidence: list[dict] = []
    for s in transcript:
        text = s.get("text") or ""
        matches = _FILLERS.findall(text)
        if matches:
            filler_hits += len(matches)
            if len(evidence) < 20:
                evidence.append({"t": round(float(s.get("start") or 0.0), 2)})
    filler_rate = 100.0 * filler_hits / n_words
    out.append(
        Metric("fillerRate", "Filler-word rate", round(filler_rate, 2), "% of words", (0, 100),
               "lexicon", confidence=0.6, group="language", evidence=evidence,
               severity=("medium" if filler_rate > 3 else "low"),
               recommendation=("Tighten script; cut fillers on jump cuts" if filler_rate > 3 else None))
    )
    out.append(
        Metric("fillerCount", "Filler-word count", filler_hits, "count", (0, 100000), "lexicon",
               confidence=0.6, group="language")
    )

    # Repetition: repeated trigrams share.
    tri = Counter(tuple(words[i : i + 3]) for i in range(len(words) - 2)) if len(words) >= 3 else Counter()
    repeated = sum(c for c in tri.values() if c > 1)
    rep_ratio = 100.0 * repeated / max(1, len(words) - 2)
    out.append(
        Metric("repetition", "Phrase repetition", round(rep_ratio, 2), "%", (0, 100), "trigram",
               confidence=0.5, group="language")
    )

    # Readability: Flesch-Kincaid grade (sentence count from segments as a proxy).
    sentences = max(1, len(re.findall(r"[.!?]+", full)) or len(transcript))
    syll = sum(_syllables(w) for w in words)
    fk = 0.39 * (n_words / sentences) + 11.8 * (syll / n_words) - 15.59
    out.append(
        Metric("readabilityGrade", "Readability (FK grade)", round(fk, 1), "grade", (0, 20),
               "flesch_kincaid", confidence=0.5, group="language",
               recommendation=("Simplify phrasing for broader reach" if fk > 11 else None))
    )

    # Intent cues.
    out.append(
        Metric("ctaPresent", "Call-to-action present", bool(_CTA.search(full)), "", None, "lexicon",
               confidence=0.6, group="language",
               recommendation=(None if _CTA.search(full) else "Add a clear CTA"))
    )
    out.append(
        Metric("promiseCue", "Promise/curiosity cue", bool(_PROMISE.search(full)), "", None, "lexicon",
               confidence=0.6, group="language")
    )
    out.append(
        Metric("questionCount", "Questions asked", len(re.findall(r"\?", full)), "count", (0, 10000),
               "punctuation", confidence=0.5, group="language")
    )

    # Safety / brand-safety.
    prof = len(_PROFANITY.findall(full))
    out.append(
        Metric("profanity", "Profanity", prof, "count", (0, 10000), "blocklist", confidence=0.5,
               group="safety", severity=("high" if prof > 3 else "medium" if prof else "low"),
               recommendation=("May affect monetization/brand safety" if prof else None))
    )
    risky = len(_RISKY_CLAIM.findall(full))
    out.append(
        Metric("riskyClaims", "Risky claims", risky, "count", (0, 10000), "lexicon", confidence=0.4,
               group="safety", severity=("medium" if risky else "low"),
               recommendation=("Review claims for policy compliance" if risky else None))
    )
    return out
