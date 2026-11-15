"""Porte de certification, diagnostic, vérification d'explication, provenance."""
from __future__ import annotations

import numpy as np

from anchoring.agent import AnchoringAgent
from anchoring.ledger import LocalChainLedger
from federation.sim import BlobStore
from fingerprint.fingerprint import bytes_fingerprint, explanation_bytes, model_fingerprint
from fingerprint.pseudonym import case_pseudonym


class NotCertified(Exception):
    """Aucun round ancré ne correspond à l'empreinte du modèle chargé."""


class CertificationGate:
    def __init__(self, ledger: LocalChainLedger, agent: AnchoringAgent, store: BlobStore):
        self.ledger, self.agent, self.store = ledger, agent, store

    def check(self, params) -> str:
        fp = model_fingerprint(params)  # recalculée sur le modèle chargé en mémoire
        if self.ledger.verify_model(fp) is None:  # indisponible => LedgerUnavailable (échec fermé)
            raise NotCertified(f"modèle {fp[:12]}… non certifié par la fédération")
        return fp

    def diagnose(self, params, x, clinic: str, patient_id: str, clinic_key: bytes, decision_id: str) -> dict:
        fp = self.check(params)
        z = float(np.dot(x, params["w"]) + params["b"][0])
        prob = float(1.0 / (1.0 + np.exp(-z)))
        explanation = {"model": fp, "bias": float(params["b"][0]),
                       "contributions": {f"f{i}": float(v) for i, v in enumerate(x * params["w"])}}
        raw = explanation_bytes(explanation)
        self.store.put_expl(decision_id, raw)
        record = {"decision_id": decision_id, "model_fp": fp, "explanation_fp": bytes_fingerprint(raw),
                  "clinic": clinic, "case": case_pseudonym(clinic_key, patient_id),
                  "probability": round(prob, 6), "status": "pending-validation"}
        self.agent.submit("decision", f"dec-{decision_id}", clinic, record)
        return record

    def verify_explanation(self, decision_id: str) -> dict:
        rec = self.ledger.verify_decision(decision_id)
        if rec is None:
            return {"ok": False, "reason": "décision non ancrée"}
        actual = bytes_fingerprint(self.store.get_expl(decision_id))
        ok = actual == rec["explanation_fp"]
        return {"ok": ok, "anchored": rec["explanation_fp"], "actual": actual,
                "reason": None if ok else "explication modifiée après sa remise"}
