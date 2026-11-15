"""Démonstration : fédération de 3 cliniques, 5 rounds, diagnostic, page d'audit HTML."""
import os, sys
from federation.sim import make_data, run_federation
from scenarios.common import KEY, build
from ui.audit_report import render

out = sys.argv[1] if len(sys.argv) > 1 else "examples"
os.makedirs(out, exist_ok=True)
tmp, ledger, agent, store, gate = build(out)
clinics, test = make_data(3, seed=1)
res = run_federation(clinics, test, 5, agent=agent, store=store)
for h in res["history"]:
    print(f"round {h['round']}  accuracy={h['accuracy']:.3f}  modèle={h['fingerprint'][:12]}…")
dec = gate.diagnose(res["params"], test[0][0], "clinicA", "patient-42", KEY, "demo-1")
print("diagnostic :", dec)
print("explication intègre :", gate.verify_explanation("demo-1")["ok"], "| chaîne valide :", ledger.verify_chain())
open(os.path.join(out, "audit.html"), "w", encoding="utf-8").write(render(ledger.decision_provenance("demo-1")))
print("page d'audit :", os.path.join(out, "audit.html"))
