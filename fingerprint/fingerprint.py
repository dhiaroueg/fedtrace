"""Empreintes canoniques (FedTrace-v1). Sans dépendance hors NumPy.

Un même jeu de paramètres doit toujours donner la même empreinte, quel que soit
l'ordre des clés, le processus ou la machine.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any, Mapping

import numpy as np

PREFIX = b"FedTrace-v1\n"


def canonical_json(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode("utf-8")


def _normalise(arr: Any, name: str) -> np.ndarray:
    a = np.asarray(arr, dtype="<f4")
    if not np.all(np.isfinite(a)):
        raise ValueError(f"valeur NaN ou infinie dans le tenseur {name!r}")
    # -0.0 + 0.0 == +0.0 (IEEE 754) : normalise le zéro négatif
    a = a + np.float32(0.0)
    return np.ascontiguousarray(a)


def model_fingerprint(params: Mapping[str, Any]) -> str:
    """SHA-256(préfixe, en-tête JSON canonique, octets des tenseurs triés par nom)."""
    names = sorted(params)
    tensors = [_normalise(params[n], n) for n in names]
    header = canonical_json(
        [{"name": n, "dtype": "float32", "shape": list(t.shape)} for n, t in zip(names, tensors)]
    )
    h = hashlib.sha256()
    h.update(PREFIX)
    h.update(len(header).to_bytes(8, "big"))
    h.update(header)
    for t in tensors:
        h.update(t.tobytes(order="C"))
    return h.hexdigest()


def _round_floats(obj: Any, ndigits: int = 6) -> Any:
    if isinstance(obj, float):
        r = round(obj, ndigits)
        return 0.0 if r == 0 else r
    if isinstance(obj, dict):
        return {k: _round_floats(v, ndigits) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_round_floats(v, ndigits) for v in obj]
    return obj


def explanation_bytes(explanation: Any) -> bytes:
    """Octets canoniques d'une explication (flottants arrondis à 6 décimales)."""
    return canonical_json(_round_floats(explanation))


def bytes_fingerprint(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
