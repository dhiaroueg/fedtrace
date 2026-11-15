"""Fédération simulée (régression logistique en NumPy) avec ancrage optionnel.

Configurations de mesure : A = fédération seule ; B = ancrage des modèles ;
C = ancrage des contributions + des modèles (+ porte de certification côté services).
Pour la version Flower + PyTorch, voir README (adaptateur AnchoringStrategy).
"""
from __future__ import annotations

import os
from typing import Dict, List, Optional

import numpy as np

from anchoring.agent import AnchoringAgent
from anchoring.ledger import AGGREGATOR
from fingerprint.fingerprint import model_fingerprint
from .strategies import fedavg, multikrum


def make_data(n_clinics: int, n_per: int = 200, d: int = 8, seed: int = 0):
    rng = np.random.default_rng(seed)
    w_true = rng.normal(size=d)
    clinics = []
    for i in range(n_clinics):
        shift = rng.normal(scale=0.3, size=d)  # léger non-IID
        X = rng.normal(size=(n_per, d)) + shift
        y = ((X @ w_true + rng.normal(scale=0.5, size=n_per)) > 0).astype(np.float64)
        clinics.append((X, y))
    Xt = rng.normal(size=(1000, d))
    yt = ((Xt @ w_true) > 0).astype(np.float64)
    return clinics, (Xt, yt)


def _sigmoid(z):
    return 1.0 / (1.0 + np.exp(-np.clip(z, -30, 30)))


def local_train(params: Dict[str, np.ndarray], X, y, epochs: int = 5, lr: float = 0.5):
    w, b = params["w"].astype(np.float64).copy(), params["b"].astype(np.float64).copy()
    for _ in range(epochs):
        p = _sigmoid(X @ w + b)
        w -= lr * (X.T @ (p - y)) / len(y)
        b -= lr * np.mean(p - y)
    return {"w": w.astype(np.float32), "b": b.astype(np.float32)}


def accuracy(params, X, y) -> float:
    return float(np.mean((_sigmoid(X @ params["w"] + params["b"]) > 0.5) == y))


def _flat(p):
    return np.concatenate([p["w"].ravel(), p["b"].ravel()]).astype(np.float64)


def _unflat(v, d):
    return {"w": v[:d].astype(np.float32), "b": v[d:].astype(np.float32)}


class BlobStore:
    """Stockage hors chaîne : poids et explications, nommés par leur empreinte / identifiant."""

    def __init__(self, root: str):
        self.root = root
        os.makedirs(os.path.join(root, "models"), exist_ok=True)
        os.makedirs(os.path.join(root, "explanations"), exist_ok=True)

    def put_model(self, fp: str, params):
        np.savez(os.path.join(self.root, "models", fp + ".npz"), **params)

    def get_model(self, fp: str):
        z = np.load(os.path.join(self.root, "models", fp + ".npz"))
        params = {k: z[k] for k in z.files}
        if model_fingerprint(params) != fp:
            raise ValueError("poids stockés altérés : l'empreinte ne correspond plus")
        return params

    def put_expl(self, decision_id: str, raw: bytes):
        with open(os.path.join(self.root, "explanations", decision_id + ".json"), "wb") as f:
            f.write(raw)

    def get_expl(self, decision_id: str) -> bytes:
        with open(os.path.join(self.root, "explanations", decision_id + ".json"), "rb") as f:
            return f.read()


def run_federation(clinics, test, rounds: int, strategy: str = "fedavg",
                   attackers: Optional[Dict[int, str]] = None, config: str = "C",
                   agent: Optional[AnchoringAgent] = None, store: Optional[BlobStore] = None,
                   f: int = 1, epochs: int = 5, privacy: Optional[dict] = None,
                   on_round=None) -> dict:
    attackers = attackers or {}
    names = [f"clinic{chr(65 + i)}" for i in range(len(clinics))]
    d = clinics[0][0].shape[1]
    glob = {"w": np.zeros(d, np.float32), "b": np.zeros(1, np.float32)}
    fp = model_fingerprint(glob)
    anchor_model = config in ("B", "C") and agent is not None
    anchor_contrib = config == "C" and agent is not None
    if store:
        store.put_model(fp, glob)
    if anchor_model:
        agent.submit("model", "model-0", AGGREGATOR, {
            "round": 0, "fingerprint": fp, "strategy": "genesis", "kept": [], "rejected": [],
            "metrics": {"accuracy": accuracy(glob, *test)}, "parent": None})
    history = [{"round": 0, "fingerprint": fp, "accuracy": accuracy(glob, *test), "kept": [], "rejected": []}]
    for r in range(1, rounds + 1):
        updates, samples, ufps = [], [], []
        for i, (X, y) in enumerate(clinics):
            p = local_train(glob, X, y, epochs=epochs)
            if i in attackers:  # empoisonnement : retournement de signe amplifié
                p = {k: (glob[k] - 5.0 * (p[k] - glob[k])).astype(np.float32) for k in p}
            ufp = model_fingerprint(p)
            updates.append(_flat(p)); samples.append(len(y)); ufps.append(ufp)
            if anchor_contrib:  # AVANT l'agrégation
                agent.submit("contribution", f"contrib-{r}-{names[i]}", names[i], {
                    "round": r, "clinic": names[i], "fingerprint": ufp, "samples": len(y),
                    "privacy": privacy or {"dp": False}, "base_model": fp})
        if strategy == "multikrum":
            kept_i, rej_i, scores = multikrum(updates, f)
        else:
            kept_i, rej_i = list(range(len(updates))), []
        agg = fedavg([updates[i] for i in kept_i], [samples[i] for i in kept_i])
        new = _unflat(agg, d)
        nfp = model_fingerprint(new)
        acc = accuracy(new, *test)
        if store:
            store.put_model(nfp, new)
        kept_names = [names[i] for i in kept_i]
        rej_recs = [{"clinic": names[i], "reason": "multikrum-outlier", "score": s} for i, s in rej_i]
        if anchor_model:
            agent.submit("model", f"model-{r}", AGGREGATOR, {
                "round": r, "fingerprint": nfp, "strategy": strategy,
                "kept": kept_names if anchor_contrib else [],
                "rejected": rej_recs if anchor_contrib else [],
                "metrics": {"accuracy": acc}, "parent": fp})
        glob, fp = new, nfp
        history.append({"round": r, "fingerprint": nfp, "accuracy": acc,
                        "kept": kept_names, "rejected": rej_recs})
        if on_round:
            on_round(r)
    return {"params": glob, "fingerprint": fp, "history": history, "names": names}
