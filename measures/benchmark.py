"""Mesures : surcoût par round (A/B/C), octets écrits vs taille du modèle, temps de provenance.
Usage : python -m measures.benchmark [repetitions]   -> measures/results.csv
"""
import csv, os, statistics as st, sys, tempfile, time
from anchoring.agent import AnchoringAgent
from anchoring.ledger import LocalChainLedger
from federation.sim import BlobStore, make_data, run_federation

REPS = int(sys.argv[1]) if len(sys.argv) > 1 else 5
ROUNDS = 10
rows = []
for d in (8, 512, 8192):                      # 3 tailles de modèle
    clinics, test = make_data(3, n_per=100, d=d, seed=3)
    for config in ("A", "B", "C"):
        times, written, prov = [], [], []
        for _ in range(REPS):
            tmp = tempfile.mkdtemp()
            ledger = LocalChainLedger(os.path.join(tmp, "l.json"))
            agent = AnchoringAgent(ledger, os.path.join(tmp, "o.db"))
            t0 = time.perf_counter()
            res = run_federation(clinics, test, ROUNDS, config=config, agent=agent,
                                 store=BlobStore(os.path.join(tmp, "b")))
            times.append((time.perf_counter() - t0) / ROUNDS)
            written.append(ledger.bytes_written() / ROUNDS)
            if config != "A":
                t1 = time.perf_counter(); ledger.get_provenance(res["fingerprint"]); prov.append(time.perf_counter() - t1)
        rows.append({"params": d + 1, "config": config, "round_s_median": round(st.median(times), 5),
                     "bytes_per_round_median": round(st.median(written)),
                     "provenance_s_median": round(st.median(prov), 6) if prov else ""})
        print(rows[-1])
with open(os.path.join(os.path.dirname(__file__), "results.csv"), "w", newline="") as f:
    w = csv.DictWriter(f, fieldnames=list(rows[0])); w.writeheader(); w.writerows(rows)
