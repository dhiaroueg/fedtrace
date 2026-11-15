"""Les cinq scénarios de démonstration du sujet, de bout en bout."""
import numpy as np
import pytest
from anchoring.ledger import LedgerUnavailable
from federation.sim import accuracy, local_train, make_data, run_federation
from fingerprint.fingerprint import model_fingerprint
from scenarios.common import KEY, build
from services.gate import NotCertified


def nominal(rounds=5, n=3, **kw):
    tmp, ledger, agent, store, gate = build()
    clinics, test = make_data(n, seed=1)
    res = run_federation(clinics, test, rounds, agent=agent, store=store, **kw)
    return ledger, agent, store, gate, clinics, test, res


def test_1_nominal():
    ledger, agent, store, gate, clinics, test, res = nominal()
    assert agent.pending() == 0 and not agent.rejected() and ledger.verify_chain()
    assert res["history"][-1]["accuracy"] > 0.85
    x = test[0][0]
    dec = gate.diagnose(res["params"], x, "clinicA", "patient-42", KEY, "d1")
    assert ledger.verify_decision("d1")["explanation_fp"] == dec["explanation_fp"]
    prov = ledger.decision_provenance("d1")
    depth, node = 0, prov["model"]
    while node:
        depth += 1
        assert node["round"] == 5 - depth + 1
        if node["round"] > 0:
            assert len(node["contributions"]) == 3
        node = node["parent"]
    assert depth == 6  # rounds 5..0 : remonte jusqu'au modèle initial
    assert gate.verify_explanation("d1")["ok"]


def test_2_explanation_falsified():
    ledger, agent, store, gate, clinics, test, res = nominal(rounds=2)
    gate.diagnose(res["params"], test[0][0], "clinicA", "p1", KEY, "d2")
    raw = store.get_expl("d2")
    store.put_expl("d2", raw.replace(b'"f0":', b'"f0":9,"x":', 1))  # retouche discrète du texte stocké
    out = gate.verify_explanation("d2")
    assert not out["ok"] and "modifiée" in out["reason"]


def test_3_uncertified_model_refused():
    ledger, agent, store, gate, clinics, test, res = nominal(rounds=2)
    outsider = local_train({"w": np.zeros(8, np.float32), "b": np.zeros(1, np.float32)}, *clinics[0], epochs=20)
    assert model_fingerprint(outsider) != res["fingerprint"]
    with pytest.raises(NotCertified):
        gate.diagnose(outsider, test[0][0], "clinicA", "p1", KEY, "d3")
    assert ledger.verify_decision("d3") is None  # rien d'ancré


def test_3b_swapped_weights_in_store_detected():
    ledger, agent, store, gate, clinics, test, res = nominal(rounds=2)
    p = store.get_model(res["fingerprint"])
    p["w"][0] += 0.01
    store.put_model(res["fingerprint"], p)
    with pytest.raises(ValueError):
        store.get_model(res["fingerprint"])


def test_4_malicious_clinic_robust_vs_naive():
    # robuste : écartée à chaque round, rejet ancré
    ledger, agent, store, gate, clinics, test, res = nominal(rounds=4, n=5, strategy="multikrum",
                                                              attackers={4: "signflip"}, f=1)
    assert all(h["rejected"] and h["rejected"][0]["clinic"] == "clinicE" for h in res["history"][1:])
    prov = ledger.get_provenance(res["fingerprint"])
    assert any(c["clinic"] == "clinicE" and c["status"] == "rejected" for c in prov["contributions"])
    assert ledger.state["CONTRIB~1~clinicE"]  # ancrée AVANT l'agrégation
    acc_robust = res["history"][-1]["accuracy"]
    # naïve : la contribution est intégrée, visible au registre
    ledger2, _, _, _, _, test2, res2 = nominal(rounds=4, n=5, strategy="fedavg", attackers={4: "signflip"})
    prov2 = ledger2.get_provenance(res2["fingerprint"])
    assert any(c["clinic"] == "clinicE" and c["status"] == "kept" for c in prov2["contributions"])
    assert acc_robust > res2["history"][-1]["accuracy"] + 0.1


def test_5_outage_then_replay_then_audit():
    tmp, ledger, agent, store, gate = build()
    clinics, test = make_data(3, seed=2)
    seen = {}

    def outage(r):  # le registre tombe après le round 1 ; le round 2 s'entraîne pendant la panne
        if r == 1:
            ledger.available = False
        if r == 2:
            seen["pending_during_outage"] = agent.pending()
            ledger.available = True
            agent.flush()

    res = run_federation(clinics, test, 4, agent=agent, store=store, on_round=outage)
    assert seen["pending_during_outage"] == 3 + 1          # 3 contributions + 1 modèle du round 2 en file
    assert agent.pending() == 0 and not agent.rejected() and ledger.verify_chain()
    assert len(ledger.blocks) == 1 + 4 * (3 + 1)            # genèse + 4 rounds : aucune perte, aucun doublon
    gate.diagnose(res["params"], test[0][0], "clinicB", "p9", KEY, "d5")
    prov = ledger.decision_provenance("d5")["model"]
    rounds = []
    while prov:
        rounds.append(prov["round"]); prov = prov["parent"]
    assert rounds == [4, 3, 2, 1, 0]


def test_gate_fails_closed_when_ledger_down():
    ledger, agent, store, gate, clinics, test, res = nominal(rounds=1)
    ledger.available = False
    with pytest.raises(LedgerUnavailable):
        gate.diagnose(res["params"], test[0][0], "clinicA", "p1", KEY, "d6")
