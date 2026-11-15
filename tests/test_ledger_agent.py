import pytest
from anchoring.agent import AnchoringAgent
from anchoring.ledger import AGGREGATOR, LedgerRejected, LedgerUnavailable, LocalChainLedger

def contrib(r, c, fp="aa"):
    return {"round": r, "clinic": c, "fingerprint": fp, "samples": 10, "privacy": {}, "base_model": "x"}

def genesis(l):
    l.anchor_model(AGGREGATOR, {"round": 0, "fingerprint": "g0", "strategy": "genesis", "kept": [],
                                "rejected": [], "metrics": {}, "parent": None})

def test_identity_checked():
    l = LocalChainLedger()
    with pytest.raises(LedgerRejected):
        l.anchor_contribution("clinicB", contrib(1, "clinicA"))

def test_idempotent_and_conflict():
    l = LocalChainLedger()
    t1 = l.anchor_contribution("clinicA", contrib(1, "clinicA"))
    n = len(l.blocks)
    assert l.anchor_contribution("clinicA", contrib(1, "clinicA")) == t1 and len(l.blocks) == n
    with pytest.raises(LedgerRejected):
        l.anchor_contribution("clinicA", contrib(1, "clinicA", fp="bb"))

def test_model_rules():
    l = LocalChainLedger(); genesis(l)
    rec = {"round": 1, "fingerprint": "m1", "strategy": "fedavg", "kept": ["clinicA"], "rejected": [],
           "metrics": {}, "parent": "g0"}
    with pytest.raises(LedgerRejected):          # contribution citée absente
        l.anchor_model(AGGREGATOR, rec)
    l.anchor_contribution("clinicA", contrib(1, "clinicA"))
    with pytest.raises(LedgerRejected):          # pas l'agrégateur
        l.anchor_model("clinicA", rec)
    l.anchor_model(AGGREGATOR, rec)
    with pytest.raises(LedgerRejected):          # round clos : ancrage tardif
        l.anchor_contribution("clinicB", contrib(1, "clinicB"))
    with pytest.raises(LedgerRejected):          # parent inexistant
        l.anchor_model(AGGREGATOR, {**rec, "round": 2, "fingerprint": "m2", "parent": "zz", "kept": []})

def test_chain_tamper_detected():
    l = LocalChainLedger(); genesis(l)
    assert l.verify_chain()
    l.blocks[0]["tx"]["writes"]["MODEL~g0"]["strategy"] = "evil"
    assert not l.verify_chain()

def test_outbox_replay_no_loss_no_dup():
    l = LocalChainLedger(); a = AnchoringAgent(l)
    l.available = False
    a.submit("contribution", "c1", "clinicA", contrib(1, "clinicA"))
    a.submit("contribution", "c2", "clinicB", contrib(1, "clinicB"))
    a.submit("contribution", "c1", "clinicA", contrib(1, "clinicA"))  # doublon ignoré
    assert a.pending() == 2 and len(l.blocks) == 0
    l.available = True
    assert a.flush() == 2 and a.pending() == 0 and len(l.blocks) == 2
    assert a.flush() == 0
