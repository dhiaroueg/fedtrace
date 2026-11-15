# FedTrace — ancrage et vérification de la provenance d'un apprentissage fédéré

Prototype pédagogique (données non réelles, pas une infrastructure hospitalière certifiée).
La blockchain est une **porte**, pas un journal : elle fige, après chaque round, ce qui a été produit,
par qui et dans quelles conditions, puis conditionne l'usage du modèle à cette preuve.

## Ce que contient ce dépôt, et son état réel

| Dossier | Contenu | État |
|---|---|---|
| `fingerprint/` | empreinte canonique FedTrace-v1, pseudonymes HMAC | **testé** |
| `anchoring/` | interface `LedgerClient`, registre local chaîné par hachage, agent d'ancrage (outbox SQLite) | **testé** |
| `federation/` | fédération simulée (NumPy), moyenne pondérée, Multi-Krum, attaques, stockage hors chaîne | **testé** |
| `services/` | porte de certification, diagnostic + explication, vérification d'explication | **testé** |
| `scenarios/`, `tests/` | les 5 scénarios du sujet + tests unitaires (25 tests) | **passent** |
| `ui/` | **Console web interactive** (serveur Python + page unique, sans dépendance) et page HTML d'audit statique | **testé** (API + captures) |
| `measures/` | benchmark A/B/C, taille de modèle, provenance → `results.csv` | **exécuté** |
| `chaincode/` | chaincode Go pour Hyperledger Fabric (mêmes règles que le registre local) | **non compilé** ici (pas d'accès réseau) : syntaxe formatée, à compiler et tester |
| `infra/` | Docker Compose MinIO + PostgreSQL | non lancé ici |
| `docs/` | cahier des charges complet (.docx, .md), version 1, sujet original, lettre | — |

## Ce qui reste à faire (voir docs, §13)

- Réseau Fabric (une organisation par clinique + agrégateur), déploiement et test du chaincode,
  adaptateur `FabricLedger` implémentant `LedgerClient` + passerelle (Fabric Gateway SDK).
- Version Flower + PyTorch (modèle MLP, Opacus, Captum) : brancher `AnchoringStrategy` sur la stratégie Flower.
  La logique d'ancrage (`anchoring/`) et les empreintes (`fingerprint/`) se réutilisent telles quelles.
- Services FastAPI, interface React d'audit, MinIO/PostgreSQL à la place du stockage fichiers.
- Signature des contributions par les cliniques et journal local chaîné de l'agent (extensions du cahier des charges).
- Ancrage en mode « différé » uniquement (le mode « strict » est à ajouter).

## Utilisation

```bash
pip install -r requirements.txt     # numpy + pytest suffisent
python3 -m pytest -q                # 25 tests, dont les 5 scénarios et l'API de la console
python3 demo.py examples            # fédération 3 cliniques x 5 rounds -> examples/audit.html
python -m ui.server                 # console web : http://127.0.0.1:8000 (Windows : python -m ui.server)
python3 -m measures.benchmark 5     # -> measures/results.csv
```

## Les 5 scénarios (`tests/test_scenarios.py`)

1. **Nominal** : 3 cliniques, 5 rounds, diagnostic ancré, provenance remontée jusqu'au modèle initial.
2. **Explication falsifiée** : le texte stocké est modifié, la vérification détecte l'écart d'empreinte.
3. **Modèle non certifié** : un modèle entraîné hors fédération est refusé par la porte ; poids altérés détectés.
4. **Clinique malveillante** : 5 cliniques dont 1 empoisonnée ; Multi-Krum l'écarte et le rejet est ancré ;
   avec la moyenne simple elle est intégrée et visible au registre.
5. **Indisponibilité** : registre coupé en plein round, file d'attente, reprise sans perte ni doublon.

## Limites à déclarer dans le rapport

- Fédération simulée, données synthétiques découpées artificiellement.
- Le registre local est un substitut de développement : sa preuve ne vaut rien hors du processus ;
  les mesures de temps ci-dessus (`measures/results.csv`) incluent des écritures fichier et SQLite et ne
  préjugent pas des performances de Fabric. En revanche le volume écrit par round (≈ 2,3 Ko en config C)
  est constant quand la taille du modèle passe de 9 à 8 193 paramètres.
- Multi-Krum exige n ≥ 2f+3 : avec 3 cliniques, aucune tolérance ; d'où 5 cliniques pour le scénario 4.
- La blockchain prouve la cohérence du processus, pas la qualité médicale du modèle.

## Console web (`python -m ui.server`)

Sept onglets : tableau de bord (précision par round, rounds, cliniques écartées), fédération (relancer avec
stratégie, ancrage A/B/C, clinique malveillante), registre (blocs chaînés, altération d'un bloc, coupure du
registre, file de reprise, révocation d'un modèle), arbre de provenance cliquable, diagnostic (porte de
certification, contributions des caractéristiques, falsification et vérification de l'explication),
les 5 scénarios exécutés en direct, et les mesures. Thème clair/sombre. Option `--no-browser` pour ne pas
ouvrir le navigateur ; `python -m ui.server 9000` pour changer de port.
