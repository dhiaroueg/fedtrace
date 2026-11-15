"""Stratégies d'agrégation : moyenne pondérée et Multi-Krum (retourne retenues et écartées)."""
from __future__ import annotations

from typing import List, Sequence, Tuple

import numpy as np


def fedavg(updates: Sequence[np.ndarray], weights: Sequence[float]) -> np.ndarray:
    w = np.asarray(weights, dtype=np.float64)
    return np.average(np.stack(updates), axis=0, weights=w / w.sum())


def multikrum(updates: Sequence[np.ndarray], f: int, m: int | None = None
              ) -> Tuple[List[int], List[Tuple[int, float]], List[float]]:
    """Multi-Krum : exige n >= 2f + 3. Retourne (retenues, écartées avec score, scores)."""
    n = len(updates)
    if n < 2 * f + 3:
        raise ValueError(f"Multi-Krum exige n >= 2f+3 (n={n}, f={f})")
    m = m if m is not None else n - f
    U = np.stack(updates)
    d2 = ((U[:, None, :] - U[None, :, :]) ** 2).sum(-1)
    k = n - f - 2
    scores = [float(np.sort(np.delete(d2[i], i))[:k].sum()) for i in range(n)]
    order = np.argsort(scores)
    kept = sorted(int(i) for i in order[:m])
    rejected = [(int(i), scores[int(i)]) for i in order[m:]]
    return kept, rejected, scores
