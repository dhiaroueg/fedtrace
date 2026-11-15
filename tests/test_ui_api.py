"""Test de l'API de l'interface : démarre le serveur sur un port libre et l'interroge."""
import json, threading, urllib.request
from http.server import ThreadingHTTPServer
import pytest
from ui import server


@pytest.fixture(scope="module")
def base():
    server.SESSION.run(3, 3, "fedavg", False, "C")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    yield f"http://127.0.0.1:{srv.server_address[1]}"
    srv.shutdown()


def call(base, path, body=None):
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode(),
                                 headers={"Content-Type": "application/json"})
    with urllib.request.urlopen(req) as r:
        return json.load(r)


def test_state_and_page(base):
    assert call(base, "/api/state")["chain_ok"] is True
    with urllib.request.urlopen(base + "/") as r:
        assert b"FedTrace Console" in r.read()


def test_all_five_scenarios_pass_through_api(base):
    for n in range(1, 6):
        out = call(base, "/api/scenario", {"n": n})
        assert out["pass"], (n, [l for l in out["log"] if l["t"] == "bad"])


def test_ledger_tamper_and_restore(base):
    call(base, "/api/scenario", {"n": 1})
    st = call(base, "/api/ledger/tamper", {})
    assert st["chain_ok"] is False and st["first_bad"] is not None
    assert call(base, "/api/ledger/restore", {})["chain_ok"] is True


def test_revoked_model_is_refused(base):
    call(base, "/api/scenario", {"n": 1})
    call(base, "/api/revoke", {})
    assert call(base, "/api/diagnose", {"clinic": "clinicA"})["refused"] is True
