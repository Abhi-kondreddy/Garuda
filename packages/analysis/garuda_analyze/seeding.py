"""Deterministic seeding so identical input yields identical output."""

from __future__ import annotations

import os
import random

DEFAULT_SEED = 1234


def seed_everything(seed: int = DEFAULT_SEED) -> int:
    seed = int(os.environ.get("GARUDA_SEED", seed))
    random.seed(seed)
    try:
        import numpy as np

        np.random.seed(seed % (2**32 - 1))
    except Exception:
        pass
    return seed
