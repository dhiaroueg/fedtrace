"""Serveur local de l'interface FedTrace (bibliothèque standard uniquement).

Lancer :  python -m ui.server [port]      puis ouvrir http://127.0.0.1:8000
Il pilote le vrai prototype (fédération, registre local, agent d'ancrage, porte de certification).
"""
from __future__ import annotations

import copy
import csv
import json
import os
import sys
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import numpy as np

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT = os.path.dirname(ROOT)
if PROJECT not in sys.path:
    sys.path.insert(0, PROJECT)

from anchoring.ledger import AGGREGATOR, LedgerUnavailable, _h  # noqa: E402
from federation.sim import local_train, make_data, run_federation  # noqa: E402
from scenarios.common import KEY, build  # noqa: E402
from services.gate import NotCertified  # noqa: E402

STATIC = os.path.join(ROOT, "static")


def first_bad_block(ledger):
    prev = "0" * 64
    for i, b in enumerate(ledger.blocks):
        body = {"index": b["index"], "prev": b["prev"], "tx": b["tx"]}
        if b["index"] != i or b["prev"] != prev or b["hash"] != _h(body):
            return i
        prev = b["hash"]
    return None


def depth_of(node):
    rounds = []
    while node:
        rounds.append(node["round"])
        node = node["parent"]
    return rounds


class Session:
    def __init__(self):
        self.ready = False
        self.counter = 0
        self.cfg = {}
        self.ledger_backup = None
        self.expl_backup = {}

    # ---------- fédération ----------
    @staticmethod
    def _fed(n, rounds, strategy, attacker, config, f=1, seed=1, on_round_factory=None):
        if strategy == "multikrum" and n < 2 * f + 3:
            raise ValueError(f"Multi-Krum exige n ≥ 2f+3 : avec {n} cliniques, choisissez au moins {2 * f + 3} cliniques ou la moyenne pondérée.")
        tmp, ledger, agent, store, gate = build()
        clinics, test = make_data(n, seed=seed)
        attackers = {n - 1: "signflip"} if attacker else {}
        hook = on_round_factory(ledger, agent) if on_round_factory else None
        res = run_federation(clinics, test, rounds, strategy, attackers, config, agent, store, f=f, on_round=hook)
        return ledger, agent, store, gate, clinics, test, res

    def run(self, n=3, rounds=5, strategy="fedavg", attacker=False, config="C", on_round_factory=None):
        n, rounds = max(3, min(int(n), 7)), max(1, min(int(rounds), 15))
        parts = self._fed(n, rounds, strategy, bool(attacker), config, on_round_factory=on_round_factory)
        (self.ledger, self.agent, self.store, self.gate, self.clinics, self.test, self.res) = parts
        self.cfg = {"clinics": n, "rounds": rounds, "strategy": strategy, "attacker": bool(attacker), "config": config}
        self.counter, self.ledger_backup, self.expl_backup = 0, None, {}
        self.decisions = []
        self.ready = True

    # ---------- état ----------
    def state(self):
        if not self.ready:
            return {"ready": False}
        L = self.ledger
        blocks = [{"index": b["index"], "hash": b["hash"], "prev": b["prev"], "op": b["tx"]["op"],
                   "identity": b["tx"]["identity"], "keys": list(b["tx"]["writes"]), "ts": b["tx"]["ts"]}
                  for b in L.blocks]
        bad = first_bad_block(L)
        revoked = [k.split("~", 1)[1] for k in L.state if k.startswith("REVOKED~")]
        return {
            "ready": True, "cfg": self.cfg, "names": self.res["names"], "history": self.res["history"],
            "latest": self.res["fingerprint"], "blocks": blocks, "chain_ok": bad is None, "first_bad": bad,
            "available": L.available, "pending": self.agent.pending(),
            "outbox_rejected": [list(r) for r in self.agent.rejected()],
            "bytes_written": L.bytes_written(), "decisions": self.decisions, "revoked": revoked,
        }

    # ---------- diagnostic ----------
    def diagnose(self, clinic, patient, sample, model):
        params = self.res["params"]
        if model == "outsider":  # modèle entraîné hors fédération
            params = local_train({"w": np.zeros_like(params["w"]), "b": np.zeros_like(params["b"])},
                                 *self.clinics[0], epochs=20)
        self.counter += 1
        did = f"d{self.counter}"
        x = self.test[0][int(sample) % len(self.test[0])]
        try:
            rec = self.gate.diagnose(params, x, clinic, patient or "patient-0", KEY, did)
        except NotCertified as e:
            return {"refused": True, "kind": "not_certified", "reason": str(e)}
        except LedgerUnavailable:
            return {"refused": True, "kind": "unavailable",
                   "reason": "registre indisponible : la porte échoue en mode fermé (aucun diagnostic sans preuve)"}
        raw = self.store.get_expl(did)
        self.expl_backup[did] = raw
        self.decisions.append(did)
        tx = self.agent.txid(f"dec-{did}")
        return {"refused": False, "decision_id": did, "decision": rec, "explanation": json.loads(raw),
                "txid": tx, "queued": tx is None}

    def tamper_expl(self, did):
        raw = self.store.get_expl(did)
        self.store.put_expl(did, raw.replace(b'"f0":', b'"f0":9,"x":', 1))
        return {"decision_id": did}

    def restore_expl(self, did):
        self.store.put_expl(did, self.expl_backup[did])
        return {"decision_id": did}

    def verify_expl(self, did):
        return self.gate.verify_explanation(did)

    # ---------- registre ----------
    def tamper_ledger(self):
        if self.ledger_backup is None:
            self.ledger_backup = copy.deepcopy(self.ledger.blocks)
        target = next(b for b in self.ledger.blocks if b["tx"]["op"] == "AnchorContribution") \
            if any(b["tx"]["op"] == "AnchorContribution" for b in self.ledger.blocks) else self.ledger.blocks[-1]
        for v in target["tx"]["writes"].values():
            if isinstance(v, dict):
                if "samples" in v:
                    v["samples"] += 1
                else:
                    v["strategy"] = "falsifié"
                break
        return {"block": target["index"]}

    def restore_ledger(self):
        if self.ledger_backup is not None:
            self.ledger.blocks = copy.deepcopy(self.ledger_backup)
            self.ledger_backup = None

    def revoke(self):
        fp = self.res["fingerprint"]
        self.ledger.revoke_model(AGGREGATOR, fp, "révocation manuelle depuis l'interface")
        return {"fingerprint": fp}

    # ---------- scénarios ----------
    def scenario(self, n):
        log, ok = [], True

        def say(t, msg):
            nonlocal ok
            if t == "bad":
                ok = False
            log.append({"t": t, "msg": msg})

        def check(cond, good, bad_):
            say("ok" if cond else "bad", good if cond else bad_)

        if n == 1:
            title = "Scénario nominal"
            self.run(3, 5, "fedavg", False, "C")
            L, h = self.ledger, self.res["history"]
            say("info", "Fédération de 3 cliniques sur 5 rounds, ancrage des contributions et des modèles.")
            say("info", f"Précision du modèle global : {h[0]['accuracy']:.2f} → {h[-1]['accuracy']:.2f}.")
            say("info", f"{len(L.blocks)} blocs écrits, {L.bytes_written()} octets au total.")
            d = self.diagnose("clinicA", "patient-42", 0, "certified")
            check(not d["refused"], "Modèle certifié : diagnostic produit, décision et explication ancrées.", "Diagnostic refusé à tort.")
            prov = L.decision_provenance(d["decision_id"])
            check(depth_of(prov["model"]) == [5, 4, 3, 2, 1, 0], "Provenance remontée du round 5 jusqu'au modèle initial.", "Provenance incomplète.")
            check(self.verify_expl(d["decision_id"])["ok"], "Empreinte de l'explication conforme au registre.", "Explication non conforme.")
            check(L.verify_chain() and self.agent.pending() == 0, "Chaîne de blocs valide, aucune écriture en attente.", "Chaîne invalide ou écritures en attente.")
        elif n == 2:
            title = "Explication falsifiée"
            self.run(3, 3, "fedavg", False, "C")
            d = self.diagnose("clinicA", "patient-7", 1, "certified")
            say("info", "Diagnostic émis ; l'empreinte de l'explication est ancrée.")
            check(self.verify_expl(d["decision_id"])["ok"], "Avant retouche : vérification positive.", "Vérification négative avant retouche.")
            self.tamper_expl(d["decision_id"])
            say("info", "Le texte stocké hors chaîne est modifié après coup (un facteur gênant est masqué).")
            v = self.verify_expl(d["decision_id"])
            check(not v["ok"], "Falsification détectée : l'empreinte recalculée diffère de celle du registre.", "Falsification NON détectée.")
            say("info", f"Ancrée {v['anchored'][:16]}… ≠ actuelle {v['actual'][:16]}…")
        elif n == 3:
            title = "Modèle non certifié"
            self.run(3, 3, "fedavg", False, "C")
            say("info", "Un modèle entraîné hors fédération remplace le modèle déployé.")
            d = self.diagnose("clinicA", "patient-9", 2, "outsider")
            check(d["refused"], "La porte ne trouve aucun round correspondant : diagnostic refusé, rien d'ancré.", "Modèle étranger accepté !")
            p = self.store.get_model(self.res["fingerprint"])
            p["w"][0] += 0.01
            self.store.put_model(self.res["fingerprint"], p)
            try:
                self.store.get_model(self.res["fingerprint"])
                say("bad", "Poids altérés non détectés.")
            except ValueError:
                say("ok", "Poids stockés modifiés : détectés à la lecture (empreinte différente).")
            self.run(3, 3, "fedavg", False, "C")  # remet une session saine
            log.append({"t": "info", "msg": "Session remise en état."})
        elif n == 4:
            title = "Clinique malveillante"
            self.run(5, 4, "multikrum", True, "C")
            h = self.res["history"][1:]
            say("info", "5 cliniques dont clinicE envoie des mises à jour empoisonnées (signe inversé, amplifié).")
            check(all(x["rejected"] and x["rejected"][0]["clinic"] == "clinicE" for x in h),
                  "Multi-Krum écarte clinicE à chaque round.", "L'attaquante n'a pas été écartée.")
            prov = self.ledger.get_provenance(self.res["fingerprint"])
            rej = [c for c in prov["contributions"] if c["status"] == "rejected"]
            check(bool(rej), f"Rejet ancré : clinicE, score {rej[0]['score']:.3g}, tx {rej[0]['txid'][:10]}…" if rej else "", "Rejet non ancré.")
            check("CONTRIB~1~clinicE" in self.ledger.state, "Sa contribution était déjà ancrée AVANT l'agrégation : elle ne peut plus la nier.", "Contribution absente.")
            acc_r = h[-1]["accuracy"]
            naive = self._fed(5, 4, "fedavg", True, "C")
            acc_n = naive[6]["history"][-1]["accuracy"]
            kept = any(c["clinic"] == "clinicE" and c["status"] == "kept" for c in naive[0].get_provenance(naive[6]["fingerprint"])["contributions"])
            check(kept, "Rejouée avec la moyenne simple : la contribution est intégrée, visible au registre.", "Contribution non intégrée.")
            check(acc_r > acc_n + 0.1, f"Précision : {acc_r:.2f} (robuste) contre {acc_n:.2f} (moyenne simple).", "Pas d'écart de précision.")
        elif n == 5:
            title = "Indisponibilité et audit"
            seen = {}

            def factory(ledger, agent):
                def hook(r):
                    if r == 1:
                        ledger.available = False
                    if r == 2:
                        seen["pending"] = agent.pending()
                        ledger.available = True
                        agent.flush()
                return hook

            self.run(3, 4, "fedavg", False, "C", on_round_factory=factory)
            say("info", "Le registre est arrêté après le round 1 ; le round 2 s'entraîne pendant la panne.")
            check(seen["pending"] == 4, f"{seen['pending']} ancrages mis en file (3 contributions + 1 modèle).", "File inattendue.")
            check(self.agent.pending() == 0 and len(self.ledger.blocks) == 17,
                  "Redémarrage : file rejouée dans l'ordre, 17 blocs = aucune perte, aucun doublon.", "Perte ou doublon.")
            d = self.diagnose("clinicB", "patient-3", 3, "certified")
            check(depth_of(self.ledger.decision_provenance(d["decision_id"])["model"]) == [4, 3, 2, 1, 0],
                  "Audit : arbre complet remonté jusqu'au modèle initial.", "Provenance incomplète.")
        else:
            raise ValueError("scénario inconnu")
        return {"title": title, "log": log, "pass": ok}


SESSION = Session()
LOCK = threading.RLock()


def bench():
    path = os.path.join(PROJECT, "measures", "results.csv")
    if not os.path.exists(path):
        return []
    with open(path, encoding="utf-8") as f:
        return list(csv.DictReader(f))


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a):
        pass

    def _send(self, code, payload, ctype="application/json"):
        raw = payload if isinstance(payload, bytes) else json.dumps(payload, default=float).encode()
        self.send_response(code)
        self.send_header("Content-Type", ctype + "; charset=utf-8")
        self.send_header("Content-Length", str(len(raw)))
        self.send_header("Cache-Control", "no-store")
        self.end_headers()
        self.wfile.write(raw)

    def do_GET(self):
        u = urlparse(self.path)
        q = {k: v[0] for k, v in parse_qs(u.query).items()}
        try:
            with LOCK:
                if u.path in ("/", "/index.html"):
                    with open(os.path.join(STATIC, "index.html"), "rb") as f:
                        return self._send(200, f.read(), "text/html")
                if u.path == "/api/state":
                    return self._send(200, SESSION.state())
                if u.path == "/api/bench":
                    return self._send(200, bench())
                if u.path == "/api/block":
                    return self._send(200, SESSION.ledger.blocks[int(q["i"])])
                if u.path == "/api/provenance":
                    L = SESSION.ledger
                    if "decision" in q:
                        return self._send(200, L.decision_provenance(q["decision"]))
                    return self._send(200, {"decision": None, "model": L.get_provenance(q["model"])})
            self._send(404, {"error": "introuvable"})
        except LedgerUnavailable:
            self._send(503, {"error": "registre indisponible"})
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"{type(e).__name__}: {e}"})

    def do_POST(self):
        u = urlparse(self.path)
        n = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(n) or b"{}")
        S = SESSION
        try:
            with LOCK:
                p = u.path
                if p == "/api/run":
                    S.run(body.get("clinics", 3), body.get("rounds", 5), body.get("strategy", "fedavg"),
                          body.get("attacker", False), body.get("config", "C"))
                    return self._send(200, S.state())
                if p == "/api/scenario":
                    out = S.scenario(int(body["n"]))
                    out["state"] = S.state()
                    return self._send(200, out)
                if p == "/api/diagnose":
                    return self._send(200, {**S.diagnose(body.get("clinic", "clinicA"), body.get("patient", ""),
                                                         body.get("sample", 0), body.get("model", "certified")),
                                            "state": S.state()})
                if p == "/api/explanation/tamper":
                    S.tamper_expl(body["id"])
                elif p == "/api/explanation/restore":
                    S.restore_expl(body["id"])
                elif p == "/api/explanation/verify":
                    return self._send(200, S.verify_expl(body["id"]))
                elif p == "/api/ledger/tamper":
                    S.tamper_ledger()
                elif p == "/api/ledger/restore":
                    S.restore_ledger()
                elif p == "/api/outage":
                    S.ledger.available = not bool(body.get("down"))
                elif p == "/api/flush":
                    S.agent.flush()
                elif p == "/api/revoke":
                    S.revoke()
                else:
                    return self._send(404, {"error": "introuvable"})
                self._send(200, S.state())
        except Exception as e:  # noqa: BLE001
            self._send(400, {"error": f"{type(e).__name__}: {e}"})


def main():
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 8000
    SESSION.run(3, 5, "fedavg", False, "C")
    srv = ThreadingHTTPServer(("127.0.0.1", port), Handler)
    url = f"http://127.0.0.1:{port}"
    print(f"Interface FedTrace : {url}   (Ctrl+C pour arrêter)")
    if "--no-browser" not in sys.argv:
        threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()
