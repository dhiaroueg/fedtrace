import os
import tempfile

from anchoring.agent import AnchoringAgent
from anchoring.ledger import LocalChainLedger
from federation.sim import BlobStore, make_data
from services.gate import CertificationGate

KEY = b"cle-secrete-clinicA-hors-chaine"


def build(tmp=None):
    tmp = tmp or tempfile.mkdtemp(prefix="fedtrace-")
    ledger = LocalChainLedger(os.path.join(tmp, "ledger.json"))
    agent = AnchoringAgent(ledger, os.path.join(tmp, "outbox.db"))
    store = BlobStore(os.path.join(tmp, "blobs"))
    gate = CertificationGate(ledger, agent, store)
    return tmp, ledger, agent, store, gate
