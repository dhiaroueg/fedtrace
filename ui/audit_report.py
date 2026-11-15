"""Génère une page HTML d'audit autonome : rounds, arbre de provenance, vérifications."""
from __future__ import annotations

import html


def _node(n: dict) -> str:
    contribs = "".join(
        f"<li class='{c['status']}'>{html.escape(c['clinic'])} — {c['status']} — "
        f"empreinte <code>{c['fingerprint'][:12]}…</code> — {c['samples']} échantillons — "
        f"tx <code>{c['txid'][:10]}…</code>"
        + (f" — motif {html.escape(str(c.get('reason')))} (score {c.get('score'):.3g})" if c.get("reason") else "")
        + "</li>" for c in n["contributions"])
    parent = f"<div class='parent'>{_node(n['parent'])}</div>" if n["parent"] else ""
    return (f"<details open><summary>Round {n['round']} — modèle <code>{n['fingerprint'][:12]}…</code> — "
            f"{html.escape(n['strategy'])} — accuracy {n['metrics'].get('accuracy', 0):.3f} — "
            f"tx <code>{n['txid'][:10]}…</code></summary><ul>{contribs}</ul>{parent}</details>")


def render(decision_prov: dict, extra: str = "") -> str:
    d = decision_prov["decision"]
    return f"""<!doctype html><html lang="fr"><meta charset="utf-8"><title>Audit FedTrace</title>
<style>body{{font:14px system-ui;max-width:900px;margin:2rem auto;padding:0 1rem}}
.banner{{background:#fff3cd;padding:.5rem 1rem;border-radius:6px}}code{{background:#eee;padding:0 .25em}}
.rejected{{color:#b00020;font-weight:600}}.parent{{margin-left:1.5rem;border-left:2px solid #ccc;padding-left:.75rem}}</style>
<p class="banner">Prototype pédagogique — données non réelles.</p>
<h1>Audit d'une décision</h1>
<p>Décision <code>{html.escape(d['decision_id'])}</code> — cas <code>{html.escape(d['case'])}</code> —
clinique {html.escape(d['clinic'])} — probabilité {d['probability']} — tx <code>{decision_prov['txid'][:10]}…</code></p>
<p>Modèle <code>{d['model_fp'][:16]}…</code> — empreinte de l'explication <code>{d['explanation_fp'][:16]}…</code></p>
<h2>Arbre de provenance</h2>{_node(decision_prov['model'])}{extra}</html>"""
