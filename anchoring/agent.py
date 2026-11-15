"""Agent d'ancrage : file persistante (outbox SQLite) rejouée sans perte ni doublon."""
from __future__ import annotations

import json
import sqlite3
from typing import Optional

from .ledger import LedgerClient, LedgerRejected, LedgerUnavailable

_KINDS = {"contribution": "anchor_contribution", "model": "anchor_model", "decision": "anchor_decision"}


class AnchoringAgent:
    def __init__(self, ledger: LedgerClient, db_path: str = ":memory:"):
        self.ledger = ledger
        self.db = sqlite3.connect(db_path)
        self.db.execute("PRAGMA journal_mode=WAL")
        self.db.execute(
            "CREATE TABLE IF NOT EXISTS outbox("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, idem TEXT UNIQUE, kind TEXT, identity TEXT, "
            "payload TEXT, status TEXT DEFAULT 'pending', attempts INTEGER DEFAULT 0, "
            "txid TEXT, error TEXT)"
        )
        self.db.commit()

    def submit(self, kind: str, idem: str, identity: str, payload: dict, flush: bool = True) -> None:
        if kind not in _KINDS:
            raise ValueError(kind)
        # INSERT OR IGNORE : un même identifiant d'idempotence n'est jamais ajouté deux fois
        self.db.execute(
            "INSERT OR IGNORE INTO outbox(idem, kind, identity, payload) VALUES (?,?,?,?)",
            (idem, kind, identity, json.dumps(payload)),
        )
        self.db.commit()
        if flush:
            self.flush()

    def flush(self) -> int:
        """Envoie les ancrages en attente, dans l'ordre. Retourne le nombre envoyé."""
        sent = 0
        rows = self.db.execute(
            "SELECT id, kind, identity, payload FROM outbox WHERE status='pending' ORDER BY id"
        ).fetchall()
        for rid, kind, identity, payload in rows:
            try:
                txid = getattr(self.ledger, _KINDS[kind])(identity, json.loads(payload))
            except LedgerUnavailable:
                self.db.execute("UPDATE outbox SET attempts=attempts+1 WHERE id=?", (rid,))
                self.db.commit()
                break  # on conserve l'ordre : contributions avant modèle
            except LedgerRejected as e:
                self.db.execute("UPDATE outbox SET status='rejected', error=? WHERE id=?", (str(e), rid))
            else:
                self.db.execute("UPDATE outbox SET status='done', txid=? WHERE id=?", (txid, rid))
                sent += 1
            self.db.commit()
        return sent

    def pending(self) -> int:
        return self.db.execute("SELECT COUNT(*) FROM outbox WHERE status='pending'").fetchone()[0]

    def rejected(self) -> list:
        return self.db.execute("SELECT idem, error FROM outbox WHERE status='rejected'").fetchall()

    def txid(self, idem: str) -> Optional[str]:
        r = self.db.execute("SELECT txid FROM outbox WHERE idem=?", (idem,)).fetchone()
        return r[0] if r else None
