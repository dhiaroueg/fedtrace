"""Interface LedgerClient et registre local chaîné par hachage (LocalChainLedger).

Mêmes règles de validation que le chaincode Go (chaincode/fedtrace.go) :
 - une contribution ne peut être écrite que par sa propre clinique, avant la clôture du round ;
 - un modèle ne peut être écrit que par l'agrégateur, avec un parent existant ;
 - une décision ne peut citer qu'un modèle ancré et non révoqué.
"""
from __future__ import annotations

import hashlib
import json
import os
import time
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

AGGREGATOR = "aggregator"


class LedgerUnavailable(Exception):
    """Le registre ne répond pas (arrêt, réseau)."""


class LedgerRejected(Exception):
    """Écriture refusée par les règles de validation."""


def _h(obj: Any) -> str:
    raw = json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()
    return hashlib.sha256(raw).hexdigest()


class LedgerClient(ABC):
    @abstractmethod
    def anchor_contribution(self, identity: str, record: dict) -> str: ...

    @abstractmethod
    def anchor_model(self, identity: str, record: dict) -> str: ...

    @abstractmethod
    def anchor_decision(self, identity: str, record: dict) -> str: ...

    @abstractmethod
    def verify_model(self, fingerprint: str) -> Optional[dict]: ...

    @abstractmethod
    def verify_decision(self, decision_id: str) -> Optional[dict]: ...

    @abstractmethod
    def get_provenance(self, fingerprint: str) -> dict: ...

    @abstractmethod
    def get_history(self, key: str) -> List[dict]: ...


class LocalChainLedger(LedgerClient):
    def __init__(self, path: Optional[str] = None):
        self.path = path
        self.blocks: List[dict] = []
        self.state: Dict[str, Any] = {}
        self.history: Dict[str, List[int]] = {}
        self.available = True
        if path and os.path.exists(path):
            self._load()

    # -- infrastructure -------------------------------------------------
    def _up(self) -> None:
        if not self.available:
            raise LedgerUnavailable("registre indisponible")

    def _append(self, identity: str, op: str, writes: Dict[str, Any]) -> str:
        prev = self.blocks[-1]["hash"] if self.blocks else "0" * 64
        tx = {"op": op, "identity": identity, "writes": writes, "ts": time.time()}
        body = {"index": len(self.blocks), "prev": prev, "tx": tx}
        block = {**body, "hash": _h(body)}
        self.blocks.append(block)
        for k, v in writes.items():
            self.state[k] = v
            self.history.setdefault(k, []).append(block["index"])
        self._persist()
        return block["hash"]

    def _persist(self) -> None:
        if self.path:
            with open(self.path, "w", encoding="utf-8") as f:
                json.dump(self.blocks, f)

    def _load(self) -> None:
        with open(self.path, encoding="utf-8") as f:
            self.blocks = json.load(f)
        for b in self.blocks:
            for k, v in b["tx"]["writes"].items():
                self.state[k] = v
                self.history.setdefault(k, []).append(b["index"])

    def verify_chain(self) -> bool:
        prev = "0" * 64
        for i, b in enumerate(self.blocks):
            body = {"index": b["index"], "prev": b["prev"], "tx": b["tx"]}
            if b["index"] != i or b["prev"] != prev or b["hash"] != _h(body):
                return False
            prev = b["hash"]
        return True

    def bytes_written(self) -> int:
        return sum(len(json.dumps(b)) for b in self.blocks)

    def _txid(self, key: str) -> str:
        return self.blocks[self.history[key][-1]]["hash"]

    # -- écritures ------------------------------------------------------
    def anchor_contribution(self, identity: str, record: dict) -> str:
        self._up()
        clinic, rnd = record["clinic"], record["round"]
        key = f"CONTRIB~{rnd}~{clinic}"
        if identity != clinic:
            raise LedgerRejected(f"identité {identity!r} différente de la clinique {clinic!r}")
        if key in self.state:
            if self.state[key]["fingerprint"] == record["fingerprint"]:
                return self._txid(key)  # idempotent
            raise LedgerRejected("contribution déjà ancrée avec une autre empreinte")
        if f"ROUND~{rnd}" in self.state:
            raise LedgerRejected("round clos : ancrage tardif refusé")
        return self._append(identity, "AnchorContribution", {key: record})

    def anchor_model(self, identity: str, record: dict) -> str:
        self._up()
        if identity != AGGREGATOR:
            raise LedgerRejected("seul l'agrégateur ancre un modèle")
        rnd, fp = record["round"], record["fingerprint"]
        rkey, mkey = f"ROUND~{rnd}", f"MODEL~{fp}"
        if rkey in self.state:
            if self.state[rkey] == fp:
                return self._txid(mkey)  # idempotent
            raise LedgerRejected("un modèle existe déjà pour ce round")
        parent = record.get("parent")
        if rnd == 0:
            if parent is not None:
                raise LedgerRejected("le modèle initial n'a pas de parent")
        else:
            p = self.state.get(f"MODEL~{parent}")
            if p is None or p["round"] != rnd - 1:
                raise LedgerRejected("parent inexistant ou round incohérent")
        for clinic in list(record.get("kept", [])) + [r["clinic"] for r in record.get("rejected", [])]:
            if f"CONTRIB~{rnd}~{clinic}" not in self.state:
                raise LedgerRejected(f"contribution de {clinic} absente du round {rnd}")
        return self._append(identity, "AnchorModel", {mkey: record, rkey: fp})

    def anchor_decision(self, identity: str, record: dict) -> str:
        self._up()
        key = f"DEC~{record['decision_id']}"
        if identity != record["clinic"]:
            raise LedgerRejected("identité différente de la clinique émettrice")
        if f"MODEL~{record['model_fp']}" not in self.state or f"REVOKED~{record['model_fp']}" in self.state:
            raise LedgerRejected("modèle inconnu ou révoqué")
        if key in self.state:
            if self.state[key] == record:
                return self._txid(key)
            raise LedgerRejected("décision déjà ancrée avec un autre contenu")
        return self._append(identity, "AnchorDecision", {key: record})

    def revoke_model(self, identity: str, fingerprint: str, reason: str) -> str:
        self._up()
        if identity != AGGREGATOR:
            raise LedgerRejected("seul l'agrégateur révoque un modèle")
        if f"MODEL~{fingerprint}" not in self.state:
            raise LedgerRejected("modèle inconnu")
        return self._append(identity, "RevokeModel", {f"REVOKED~{fingerprint}": {"reason": reason}})

    # -- lectures -------------------------------------------------------
    def verify_model(self, fingerprint: str) -> Optional[dict]:
        self._up()
        if f"REVOKED~{fingerprint}" in self.state:
            return None
        return self.state.get(f"MODEL~{fingerprint}")

    def verify_decision(self, decision_id: str) -> Optional[dict]:
        self._up()
        return self.state.get(f"DEC~{decision_id}")

    def get_provenance(self, fingerprint: str) -> dict:
        self._up()
        rec = self.state.get(f"MODEL~{fingerprint}")
        if rec is None:
            raise KeyError(fingerprint)
        node = {
            "round": rec["round"],
            "fingerprint": fingerprint,
            "strategy": rec["strategy"],
            "metrics": rec["metrics"],
            "txid": self._txid(f"MODEL~{fingerprint}"),
            "contributions": [self._contrib(rec["round"], c, False) for c in rec.get("kept", [])]
            + [self._contrib(rec["round"], r["clinic"], True, r) for r in rec.get("rejected", [])],
            "parent": self.get_provenance(rec["parent"]) if rec.get("parent") else None,
        }
        return node

    def _contrib(self, rnd: int, clinic: str, rejected: bool, why: Optional[dict] = None) -> dict:
        key = f"CONTRIB~{rnd}~{clinic}"
        c = self.state[key]
        out = {"clinic": clinic, "fingerprint": c["fingerprint"], "samples": c["samples"],
               "txid": self._txid(key), "status": "rejected" if rejected else "kept"}
        if why:
            out["reason"] = why.get("reason")
            out["score"] = why.get("score")
        return out

    def decision_provenance(self, decision_id: str) -> dict:
        d = self.verify_decision(decision_id)
        if d is None:
            raise KeyError(decision_id)
        return {"decision": d, "txid": self._txid(f"DEC~{decision_id}"),
                "model": self.get_provenance(d["model_fp"])}

    def get_history(self, key: str) -> List[dict]:
        self._up()
        return [self.blocks[i] for i in self.history.get(key, [])]
