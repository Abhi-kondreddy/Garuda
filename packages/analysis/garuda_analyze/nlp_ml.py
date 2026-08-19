"""ML/NLP parameters: lexicon sentiment (always) + transformer NER/topics (opt)."""

from __future__ import annotations

import re

from .metrics import REGISTRY, Metric, unavailable
from .models import MODELS

_WORD = re.compile(r"[a-z']+")
_POS = {
    "amazing", "great", "love", "best", "awesome", "incredible", "perfect", "win", "wins",
    "happy", "excited", "beautiful", "easy", "powerful", "boost", "growth", "success", "good",
    "wonderful", "fantastic", "brilliant", "improve", "improved", "better", "gain",
}
_NEG = {
    "bad", "worst", "hate", "boring", "hard", "difficult", "fail", "failed", "problem", "issue",
    "wrong", "ugly", "slow", "confusing", "annoying", "terrible", "awful", "broken", "risk",
    "loss", "lose", "angry", "sad", "fear", "worried",
}


def _sentiment(words: list[str]) -> float:
    pos = sum(w in _POS for w in words)
    neg = sum(w in _NEG for w in words)
    tot = pos + neg
    return (pos - neg) / tot if tot else 0.0


@REGISTRY.register("nlp_ml", group="language")
def _nlp_ml(ctx: dict) -> "list[Metric]":
    tx = ctx.get("transcript") or []
    if not tx:
        return [unavailable("sentiment", "Overall sentiment", "lexicon", "language", "No transcript")]

    out: list[Metric] = []
    words = _WORD.findall(" ".join((s.get("text") or "") for s in tx).lower())
    out.append(
        Metric("sentiment", "Overall sentiment", round(_sentiment(words), 3), "score", (-1, 1),
               "lexicon", confidence=0.4, group="language")
    )

    # Sentiment arc over thirds.
    n = len(tx)
    if n >= 3:
        thirds = [tx[: n // 3], tx[n // 3 : 2 * n // 3], tx[2 * n // 3 :]]
        arc = [
            round(_sentiment(_WORD.findall(" ".join((s.get("text") or "") for s in part).lower())), 3)
            for part in thirds
        ]
        out.append(
            Metric("sentimentArc", "Sentiment arc (thirds)", arc, "score", (-1, 1), "lexicon",
                   confidence=0.4, group="language")
        )

    # NER / topics require a transformer model.
    has_transformers = False
    try:
        import transformers  # noqa: F401

        has_transformers = True
    except Exception:
        has_transformers = False
    if not (has_transformers or MODELS.available("ner")):
        out.append(unavailable("namedEntities", "Named entities", "transformer", "language", "Model not bundled"))
        out.append(unavailable("topics", "Topic segmentation", "transformer", "language", "Model not bundled"))
    return out
