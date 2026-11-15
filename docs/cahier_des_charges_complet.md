---
title: "Cahier des charges complet — FedTrace"
subtitle: "Ancrage et vérification de la provenance d’un apprentissage fédéré pour le diagnostic des maladies auto-immunes"
author: "Mini-projet 2026-2027 · Version 1.0"
date: "13 novembre 2026"
lang: fr-FR
toc: true
toc-title: "Sommaire"
---

# 1. Objet du document

Ce document transforme le sujet FedTrace en spécification exploitable par l’équipe : exigences, architecture, choix technologiques justifiés, critères d’acceptation, planning et risques. Les décisions techniques du §7 sont des **propositions argumentées** ; elles devront être reprises dans la note de choix technologique (livrable demandé par le sujet).

Principe directeur : la blockchain est une **porte**, pas un journal. Elle intervient après chaque round pour figer ce qui a été produit, par qui et dans quelles conditions, puis conditionne l’usage du modèle à la présence de cette preuve.

# 2. Objectifs

- **O1** : faire tourner une fédération d’au moins 3 cliniques sur plusieurs rounds, avec ancrage des contributions (avant agrégation) et des modèles globaux (après agrégation).
- **O2** : refuser tout diagnostic produit par un modèle dont l’empreinte n’est pas ancrée (porte de certification).
- **O3** : ancrer chaque diagnostic avec l’empreinte du modèle et celle de l’explication, puis reconstituer l’historique complet depuis un diagnostic jusqu’au modèle initial.
- **O4** : détecter une explication falsifiée, un modèle non certifié et une clinique malveillante, et le prouver dans l’interface d’audit.
- **O5** : mesurer le coût de l’ancrage et comparer trois configurations (fédération seule, ancrage des modèles, ancrage des contributions + porte de certification).

# 3. Périmètre et hypothèses

**Inclus** : fédération simulée (processus distincts sur une machine), registre permissionné, contrat intelligent, agent d’ancrage, porte de certification, service de provenance, interface d’audit, mesures.

**Exclus** : données de patients réels, certification hospitalière, haute disponibilité, optimisation de la précision médicale (le projet se juge sur les propriétés de vérification, pas sur l’accuracy).

**Hypothèses** : les données sont synthétiques ou issues d’un jeu public (licence à vérifier), découpées artificiellement entre cliniques ; ce point doit être déclaré dans le rapport. Aucun GPU n’est nécessaire (modèle tabulaire léger). Poste de référence : Linux ou WSL2, 4 cœurs, 16 Go de RAM, Docker.

# 4. Acteurs

| Acteur | Rôle dans le système |
|:--------------------|:----------------------------------------------------------|
| Clinique (N ≥ 3) | entraîne localement, ancre sa contribution, émet des diagnostics |
| Agrégateur | agrège, ancre le modèle global et le sort de chaque contribution |
| Clinicien | soumet un cas, reçoit diagnostic et explication |
| Auditeur | vérifie une décision, remonte l’arbre de provenance |
| Clinique malveillante | acteur simulé pour les scénarios d’attaque |

# 5. Exigences fonctionnelles

Priorités MoSCoW : M = indispensable, S = souhaitable, C = extension.

| ID | Exigence | Prio |
|:------|:--------------------------------------------------------------------|:---|
| EF-01 | Fédération de ≥ 3 cliniques (processus distincts), plusieurs rounds | M |
| EF-02 | Deux stratégies : moyenne pondérée et stratégie robuste exposant la liste des contributions retenues et écartées | M |
| EF-03 | Empreinte déterministe de chaque mise à jour locale, avant agrégation | M |
| EF-04 | Ancrage de la contribution : empreinte, identité de la clinique, nombre d’échantillons déclaré, paramètres de confidentialité, horodatage | M |
| EF-05 | Ancrage du modèle global : empreinte, stratégie, contributions retenues/écartées, métriques, référence du round parent | M |
| EF-06 | Porte de certification : refus du diagnostic si l’empreinte du modèle chargé ne correspond à aucun round | M |
| EF-07 | Diagnostic avec explication ; ancrage des empreintes du modèle et de l’explication | M |
| EF-08 | Pseudonymisation des cas ; aucune donnée identifiante sur la chaîne | M |
| EF-09 | Reconstitution de la provenance : diagnostic → modèle → round → contributions → rounds parents → modèle initial | M |
| EF-10 | Détection d’une explication modifiée et d’un modèle non certifié | M |
| EF-11 | File de reprise : tout ancrage en échec est conservé puis rejoué sans perte ni doublon | M |
| EF-12 | Interface d’audit : arbre de provenance, empreintes, identifiants de transaction | M |
| EF-13 | Génération automatique du relevé de mesures | S |
| EF-14 | Signature de chaque contribution par la clé de la clinique | S |
| EF-15 | Révocation tracée d’un modèle défaillant | C |
| EF-16 | Ancrage périodique d’une racine de Merkle sur un registre public | C |

# 6. Exigences non fonctionnelles (cibles mesurables)

| Exigence | Critère d’acceptation proposé |
|:----------------|:--------------------------------------------------------------|
| Déterminisme | même modèle → même empreinte sur 100 exécutions, après sauvegarde/rechargement et entre deux machines : 100 % |
| Intégrité | toute modification hors chaîne (poids, explication) détectée : 100 % sur les cas de test |
| Confidentialité | revue automatique : aucune donnée patient ni identifiant en clair dans les transactions |
| Sécurité | seule l’organisation concernée peut écrire sa contribution ou sa décision ; chaque transaction est rattachée à une identité |
| Résilience | registre arrêté pendant un round : 0 ancrage perdu, 0 doublon après reprise |
| Performance | surcoût d’ancrage par round < 10 % du temps de round (à confirmer par les mesures) |
| Volume | octets écrits par round indépendants de la taille du modèle (testé sur 3 tailles de modèle) |
| Traçabilité | provenance d’un diagnostic reconstituée en quelques secondes pour 10 rounds |
| Modularité | fédération, ancrage, stockage et interface remplaçables derrière des interfaces explicites |
| Faux refus | taux de faux refus de la porte : 0 % sur modèles certifiés non révoqués |

# 7. Choix technologiques

## 7.1 Synthèse

| Composant | Choix recommandé | Alternative | Justification |
|:-----------|:-----------------|:-------------|:------------------------------|
| Registre distribué | **Hyperledger Fabric** (permissionné) | Hyperledger Besu (QBFT) | identités fortes par organisation, historique natif d’une clé, pas de coût par transaction |
| Contrat intelligent | **Chaincode en Go** | TypeScript | langage typé, bien documenté, exemples officiels, exécution déterministe |
| Passerelle vers le registre | **Fabric Gateway SDK (Node.js/TypeScript)** exposé en API REST interne | client Go | permet à l’agent Python de rester découplé du registre |
| Fédération | **Flower + PyTorch** | NVIDIA FLARE, implémentation maison | cadre le plus répandu, stratégies extensibles par héritage, simulation multi-processus simple |
| Modèle | MLP tabulaire (PyTorch) | régression logistique | taille réglable, utile pour la mesure du volume ancré |
| Explicabilité | **Captum** (Integrated Gradients) | SHAP | déterministe à baseline fixée, intégré à PyTorch |
| Confidentialité | **Opacus** (DP-SGD) | écrêtage + bruit manuel | paramètres (ε, δ, écrêtage, bruit) simples à ancrer |
| Empreintes | SHA-256 (hashlib) + NumPy | SHA3-256 | standard, rapide, cohérent avec les hachages du registre |
| Pseudonymes | HMAC-SHA256 à clé par clinique | hachage simple | un hachage simple se casse par dictionnaire |
| Agent d’ancrage | Python asyncio + file **SQLite** (mode WAL) | RabbitMQ, Redis | zéro infrastructure, persistant, suffisant à cette échelle |
| Services (porte, provenance) | **FastAPI** + Pydantic | Flask | validation de schémas, documentation OpenAPI automatique |
| Stockage hors chaîne | **MinIO** (blobs) + **PostgreSQL** (métadonnées) | système de fichiers adressé par contenu | poids et explications nommés par leur empreinte ; interface S3 standard |
| Interface d’audit | **React + TypeScript + Vite**, React Flow (arbre), Recharts | Streamlit | rendu professionnel de l’arbre de provenance ; Streamlit en plan B si le front-end manque de compétences |
| Déploiement | Docker Compose, Linux/WSL2 | — | reproductibilité de la démonstration |
| Qualité | pytest, go test, Vitest, ruff, mypy, GitHub Actions | — | tests de reproductibilité et des cinq scénarios automatisés |
| Mesures | time.perf_counter, journaux JSON, CSV, Jupyter (pandas, matplotlib) | Prometheus/Grafana | suffisant et plus léger |

Les versions exactes (Python, PyTorch, Flower, Fabric, Go, Node.js) sont à figer dans un fichier de versions au démarrage, en prenant les dernières versions stables ; les API de Flower et de Fabric évoluent, il ne faut pas les mettre à jour en cours de projet.

## 7.2 Étude comparative du registre

| Critère | Fabric | Besu (QBFT) | Chaîne publique (testnet) | Registre local simplifié |
|:----------|:-------------|:-------------|:-------------|:-------------|
| Identités / non-répudiation | forte (X.509, une organisation par clinique) | adresses, pas d’identité native | pseudonymes | simulée |
| Historique d’une clé | natif (GetHistoryForKey) | via événements à indexer | via événements | à coder |
| Coût par transaction | nul | nul | gas, testnet instable | nul |
| Métadonnées | limitées au consortium | limitées au consortium | publiques | locales |
| Vérifiabilité externe | limitée au consortium | limitée au consortium | forte | nulle |
| Effort d’installation | élevé | moyen | faible | nul |

**Décision** : Fabric, car le sujet exige des identités fortes, une validation par organisation et la relecture de l’historique d’une clé, ce que Fabric fournit nativement. Limite à déclarer dans le rapport : la preuve ne vaut que dans les limites du consortium. La chaîne publique est retenue seulement comme extension (EF-16). Le registre local sert à la phase 0 et de plan B.

## 7.3 Stratégie de réduction du risque : interface LedgerClient

L’agent et les services ne parlent qu’à une interface **LedgerClient** (anchor_contribution, anchor_model, anchor_decision, verify_model, verify_decision, get_provenance, get_history). Deux adaptateurs : **LocalChainLedger** (chaîne de blocs chaînés par hachage dans un fichier, mêmes règles de validation) puis **FabricLedger**. Toute la logique est validée sur le premier ; le projet reste démontrable si l’installation de Fabric dérape.

# 8. Architecture cible

## 8.1 Composants et flux

1. Chaque client Flower entraîne localement, avec Opacus si activé.
2. Le module d’empreinte calcule l’empreinte de la mise à jour ; l’agent de la clinique l’ancre sous l’identité de la clinique.
3. L’agrégateur applique la stratégie, établit la liste des contributions retenues et écartées, évalue le modèle global.
4. L’agent ancre le modèle global (empreinte, stratégie, retenues/écartées, métriques, parent) sous l’identité de l’agrégateur, et stocke les poids hors chaîne, nommés par leur empreinte.
5. Pour un diagnostic, la porte recalcule l’empreinte du modèle **chargé en mémoire** et interroge le registre ; sans round correspondant (ou modèle révoqué), réponse 403 et événement d’audit.
6. Le diagnostic et l’explication sont produits ; l’explication est écrite hors chaîne, puis les deux empreintes et la décision sont ancrées.
7. Le service de provenance remonte l’arbre ; l’interface l’affiche.

Dans Flower, l’ancrage se branche dans une sous-classe de Strategy (**AnchoringStrategy**, patron décorateur) qui intercepte l’agrégation : les contributions sont ancrées avant l’appel à l’agrégation, le modèle après.

## 8.2 Réseau Fabric

Une organisation par clinique (identité et non-répudiation individuelles) plus une organisation Agrégateur, un orderer Raft, un pair par organisation avec base d’état LevelDB, une autorité de certification par organisation, un canal unique. Partir de fabric-samples/test-network puis l’étendre à N organisations. Pour la démonstration d’attaque, prévoir 5 cliniques (voir R2) : environ 15 conteneurs, compatible avec 16 Go de RAM.

## 8.3 Modèle de données sur la chaîne

| Clé | Contenu | Écrivain autorisé | Règles de validation |
|:-------------|:---------------|:---------------|:-----------------------|
| CONTRIB\~round\~clinique | empreinte, nb d’échantillons, paramètres de confidentialité, empreinte du modèle de départ, signature optionnelle | organisation de la clinique uniquement | unique par (round, clinique) ; idempotent si même empreinte, rejet si différente |
| MODEL\~empreinte | round, stratégie et paramètres, retenues, écartées (avec motif et score), métriques, empreinte parente | organisation Agrégateur | toutes les contributions citées existent et sont du même round ; le parent existe ; un seul modèle par round |
| ROUND\~n | pointeur vers l’empreinte du modèle | Agrégateur | écrit avec MODEL |
| DEC\~identifiant | empreinte du modèle, empreinte de l’explication, clinique, pseudonyme, probabilité, statut | organisation de la clinique | le modèle existe et n’est pas révoqué |

Règles transverses : l’identité de l’appelant est lue dans le contexte du chaincode (MSP) et comparée à la clinique déclarée ; l’horodatage est celui de la transaction (jamais celui du client ni de l’heure locale) pour garder le contrat déterministe ; le round 0 ancre le modèle initial (genèse). Le modèle étant adressé par son empreinte, la vérification est une lecture directe de clé. La politique d’endossement du chaincode est à la majorité des organisations.

Opérations du contrat : AnchorContribution, AnchorModel, AnchorDecision, VerifyModel, VerifyDecision, GetModelProvenance, GetKeyHistory (et RevokeModel en extension).

# 9. Spécifications détaillées

## 9.1 Empreinte canonique d’un modèle

- Tenseurs triés par nom, convertis en float32, petit-boutiste, ordre C, mémoire contiguë.
- Valeurs NaN et infinies rejetées ; la valeur −0,0 est normalisée en 0,0.
- En-tête JSON canonique (clés triées, sans espaces, UTF-8) listant nom, type et forme de chaque tenseur.
- Empreinte = SHA-256(préfixe de version FedTrace-v1, en-tête, octets des tenseurs). Le préfixe de version évite les collisions entre usages et permet d’évoluer.
- L’empreinte porte sur l’artefact (les poids), pas sur l’entraînement : la reproductibilité exigée est celle de la sérialisation ; fixer néanmoins les graines pour rendre les expériences comparables.
- Tests : sérialiser/désérialiser, changer d’ordre de dictionnaire, relancer dans un autre processus, changer de machine ; modifier un seul bit doit changer l’empreinte.

## 9.2 Empreinte de l’explication

L’explication est écrite en JSON canonique avec flottants arrondis à 6 décimales ; l’empreinte est celle des **octets exacts stockés**. La vérification relit les octets, recalcule et compare : toute retouche, même d’une virgule, est détectée.

## 9.3 Pseudonymisation

Pseudonyme = préfixe + base32 tronquée de HMAC-SHA256(clé de la clinique, identifiant patient). La clé reste hors chaîne (secret Docker). Supprimer la clé et la table de correspondance hors chaîne rend le pseudonyme non réidentifiable : c’est la réponse proposée au droit à l’effacement, à documenter dans le rapport.

## 9.4 Agent d’ancrage et file de reprise

- Patron **outbox** : chaque ancrage est d’abord écrit dans SQLite (identifiant d’idempotence, type, charge utile, statut, nombre d’essais, prochaine tentative), puis envoyé.
- Reprise avec attente exponentielle ; relecture au redémarrage ; ordre respecté par round (contributions avant modèle).
- Le contrat étant idempotent, un rejeu ne crée pas de doublon.
- Deux modes configurables : **strict** (la publication du modèle attend l’ancrage des contributions) et **différé** (la fédération continue, le modèle reste inutilisable par la porte tant qu’il n’est pas ancré). Le scénario d’indisponibilité du sujet correspond au mode différé. Pour que la non-répudiation survive à un ancrage tardif, la clinique signe sa contribution (EF-14, à promouvoir en priorité M dans ce cas) et l’agent tient un journal local chaîné par hachage.

## 9.5 Stratégie robuste

Implémenter soi-même une sélection de type **Multi-Krum** (ou filtre par distance à la médiane et similarité cosinus) afin de connaître exactement les contributions écartées : les fonctions toutes faites de Flower ne renvoient que le résultat agrégé. Chaque écart est ancré avec son motif et son score. Attaques à simuler : retournement de signe, mise à l’échelle de la mise à jour, bruit gaussien, inversion d’étiquettes.

# 10. Sécurité, confidentialité et conformité

- Aucune donnée patient, aucun identifiant, aucun poids sur la chaîne : uniquement des empreintes, des pseudonymes et des métadonnées de processus.
- Les métadonnées (identités des cliniques, volumes, métriques) sont visibles de tout le canal : acceptable dans un consortium, à déclarer.
- Secrets (clés, certificats) hors dépôt Git ; fichier d’exemple d’environnement fourni.
- Les paramètres de confidentialité ancrés sont vérifiables, pas nécessairement protecteurs ; le budget de confidentialité n’est pas comptabilisé formellement (extension).
- Bannière « prototype pédagogique, données non réelles » dans l’interface et le dépôt.

# 11. Scénarios de démonstration et critères d’acceptation

| Scénario | Déroulé | Critère de réussite |
|:-------------|:------------------|:--------------------------------|
| 1. Nominal | 3 cliniques, plusieurs rounds, un cas soumis | pour chaque round, empreintes, stratégie, métriques et identifiants de transaction affichés ; diagnostic ancré avec les deux empreintes |
| 2. Explication falsifiée | modification du texte hors chaîne | écart d’empreinte détecté et signalé |
| 3. Modèle non certifié | remplacement par un modèle entraîné hors fédération | refus de la porte (403), événement d’audit |
| 4. Clinique malveillante | mise à jour empoisonnée, 5 cliniques dont 1 malveillante | contribution ancrée avant agrégation, écartée et rejet ancré ; rejouée avec la moyenne simple, elle est intégrée et visible au registre |
| 5. Indisponibilité et audit | arrêt du registre pendant un round | 0 perte, reprise automatique ; arbre complet remonté jusqu’au modèle initial |

Chaque scénario est un test automatisé de bout en bout, rejouable par une seule commande.

# 12. Évaluation et mesures

- **Configurations** : A = fédération seule ; B = ancrage des modèles ; C = ancrage des contributions + porte de certification.
- **Indicateurs** : surcoût temporel par round (C par rapport à A), octets écrits par round et constance en fonction de la taille du modèle (3 tailles), temps de reconstitution de provenance (1, 5, 10, 20 rounds), taux de détection des falsifications, taux de faux refus de la porte, croissance du registre par round.
- **Protocole** : au moins 10 répétitions par configuration, médiane et écart interquartile, machine et versions consignées, résultats exportés en CSV et tableaux comparatifs dans le rapport.

# 13. Plan de réalisation détaillé, de A à Z

Chaque étape précise l’objectif, les tâches, le responsable, le livrable et le critère de validation. Les étapes se suivent par phases (voir §15 pour le calendrier). Les responsables suivent la répartition : E1 Fédération, E2 Registre, E3 Ancrage, E4 Vérification, E5 Interface et mesures.

## Phase 0 — Cadrage et socle (semaines 1–2)

**Étape 0.1 — Lecture du sujet et glossaire commun (toute l’équipe).** Relire le sujet, lister les termes (round, empreinte, ancrage, porte, provenance) et valider la compréhension du flux : entraînement local → ancrage de la contribution → agrégation → ancrage du modèle → porte → diagnostic → ancrage de la décision → vérification. *Livrable* : glossaire d’une page. *Validation* : chaque membre sait expliquer le flux sans support.

**Étape 0.2 — Note de choix technologique (E2, relecture de tous).** Comparer Fabric, Besu, chaîne publique de test et registre local selon les axes du sujet (permissionné ou public, identités, règles de validation, coût et débit, relecture de l’historique d’une clé, effort d’installation). Format ADR : contexte, options, critères, décision, conséquences. *Livrable* : note de 3 à 4 pages (base : §7). *Validation* : jalon J0.

**Étape 0.3 — Dépôt et standards (E3).** Créer le dépôt Git avec la structure de l’annexe, la branche principale protégée, les pull requests obligatoires, ruff, mypy, pytest, un hook de pré-commit et une intégration continue qui lance les tests. Fournir un fichier d’exemple d’environnement et un fichier de versions figées. *Validation* : une pull request vide passe l’intégration continue.

**Étape 0.4 — Environnement de développement (tous).** Installer Linux ou WSL2, Docker et Docker Compose, Python (environnement virtuel), Go, Node.js, Git. Vérifier 16 Go de RAM et 30 Go de disque libres. *Validation* : un script de contrôle d’environnement affiche toutes les versions.

**Étape 0.5 — Jeu de données et découpage (E1).** Choisir un jeu de données tabulaire public à licence claire (par exemple un jeu de santé auto-immune ou, à défaut, un jeu synthétique généré avec scikit-learn), le découper en 3 à 5 cohortes de cliniques, avec une option de déséquilibre (non-IID). Déclarer ce découpage artificiel dans le rapport. *Livrable* : script de partition reproductible (graine fixée) et fiche du jeu de données.

**Étape 0.6 — Interface LedgerClient et registre local (E2 et E3).** Définir l’interface (anchor_contribution, anchor_model, anchor_decision, verify_model, verify_decision, get_provenance, get_history), implémenter LocalChainLedger (blocs chaînés par hachage dans un fichier, mêmes règles de validation que le futur contrat) et ses tests unitaires. *Validation* : tests verts ; falsifier un bloc casse la chaîne.

## Phase 1 — Noyau fédération et ancrage (semaines 3–5)

**Étape 1.1 — Modèle et entraînement local (E1).** Écrire le MLP PyTorch, la boucle d’entraînement locale et l’évaluation (accuracy, F1, AUC). Prévoir 3 tailles de modèle (petite, moyenne, grande) pour la mesure du volume ancré. *Validation* : le modèle apprend sur une cohorte isolée.

**Étape 1.2 — Fédération Flower (E1).** Serveur et N clients dans des processus distincts, 3 clients au minimum, plusieurs rounds, configuration par fichier. Stratégie de base : moyenne pondérée par le nombre d’échantillons. *Validation* : le modèle global progresse sur 10 rounds.

**Étape 1.3 — Module d’empreinte (E3).** Implémenter l’empreinte canonique (§9.1) avec ses tests : sérialisation puis rechargement, ordre des clés, autre processus, autre machine, un bit modifié, −0,0, NaN refusés. Ce module est écrit en premier car tout le reste en dépend. *Validation* : 100 % de reproductibilité sur 100 exécutions.

**Étape 1.4 — Pseudonymisation (E3).** HMAC-SHA256 à clé par clinique, clé fournie par secret, table de correspondance hors chaîne. *Validation* : même patient, même pseudonyme ; clés différentes, pseudonymes différents.

**Étape 1.5 — Stockage hors chaîne (E3).** Déployer MinIO et PostgreSQL par Docker Compose ; stocker les poids et explications sous leur empreinte ; lecture avec revérification de l’empreinte. *Validation* : modifier un octet stocké est détecté à la lecture.

**Étape 1.6 — Agent d’ancrage v1 (E3).** Patron outbox SQLite, envoi vers LedgerClient, identifiants d’idempotence, journal local chaîné par hachage. Brancher AnchoringStrategy dans Flower : contributions ancrées avant l’agrégation, modèle après. *Validation* : jalon J1, scénario nominal complet sur le registre local.

**Étape 1.7 — Stratégie robuste et attaques (E1).** Implémenter Multi-Krum (ou médiane et similarité cosinus) retournant la liste exacte des retenues et écartées avec scores ; implémenter les attaques (retournement de signe, mise à l’échelle, bruit, inversion d’étiquettes). *Validation* : avec 5 cliniques dont 1 malveillante, la contribution est écartée à chaque round.

## Phase 2 — Registre réel (semaines 6–8)

**Étape 2.1 — Réseau Fabric (E2, démarrage dès la semaine 3 en tâche de fond).** Installer les binaires et images Fabric, lancer le test-network, puis le passer à une organisation par clinique plus l’agrégateur, un orderer Raft, un pair et une autorité de certification par organisation. *Validation* : le chaincode de démonstration de Fabric s’exécute sur le réseau étendu.

**Étape 2.2 — Chaincode en Go (E2).** Implémenter les opérations et les règles du §8.3 : identité lue dans le MSP, unicité par (round, clinique), cohérence des contributions citées, parent existant, un seul modèle par round, horodatage de la transaction, idempotence. Tests unitaires avec le stub de simulation de Fabric. *Validation* : chaque règle de rejet a un test.

**Étape 2.3 — Passerelle (E2 et E3).** Service TypeScript avec le Fabric Gateway SDK exposant une API REST interne ; adaptateur FabricLedger implémentant LedgerClient. *Validation* : les mêmes tests d’interface passent sur LocalChainLedger et sur FabricLedger.

**Étape 2.4 — Porte de certification (E4).** Service FastAPI : recalcul de l’empreinte du modèle chargé en mémoire, interrogation du registre, 200 ou 403, événement d’audit. Mise en cache prudente (jamais un refus transformé en accord). *Validation* : modèle certifié accepté, modèle étranger refusé, taux de faux refus nul.

**Étape 2.5 — Diagnostic et explication (E4 et E1).** Prédiction, explication par Captum (baseline fixée), JSON canonique, empreinte, stockage, ancrage de la décision. *Validation* : jalon J2, scénario nominal sur Fabric avec identifiants de transaction.

**Étape 2.6 — Service de provenance (E4).** Remonter diagnostic → modèle → round → contributions → modèle parent → … → modèle initial, via GetModelProvenance et GetKeyHistory. *Validation* : arbre complet reconstitué en quelques secondes pour 10 rounds.

## Phase 3 — Scénarios, résilience et interface (semaines 9–10)

**Étape 3.1 — Scénario 2, explication falsifiée (E4).** Modifier le texte hors chaîne, recalculer, comparer ; message de falsification clair. Test automatisé.

**Étape 3.2 — Scénario 3, modèle non certifié (E4).** Entraîner un modèle hors fédération, le charger à la place du modèle certifié ; vérifier le refus et l’événement d’audit.

**Étape 3.3 — Scénario 4, clinique malveillante (E1 et E4).** 5 cliniques dont 1 malveillante : empreinte ancrée avant agrégation, rejet ancré avec motif et score ; relancer avec la moyenne simple et montrer l’intégration de la contribution au registre.

**Étape 3.4 — Scénario 5, indisponibilité (E3).** Arrêter le réseau Fabric pendant un round (mode différé), vérifier la file, redémarrer, vérifier la reprise sans perte ni doublon ; remonter ensuite l’arbre jusqu’au modèle initial.

**Étape 3.5 — Interface d’audit (E5).** React, TypeScript et Vite ; vues : liste des rounds (empreintes, stratégie, métriques, transactions), arbre de provenance avec React Flow, détail d’une décision, bouton de vérification (modèle et explication), journal des refus. Bannière « prototype pédagogique ». *Validation* : jalon J3, les cinq scénarios passent, un seul script les rejoue.

## Phase 4 — Mesures et évaluation (semaines 11–12)

**Étape 4.1 — Instrumentation (E5).** Chronométrer chaque étape d’un round (entraînement, empreinte, ancrage, agrégation, publication) avec perf_counter, écrire des journaux JSON horodatés puis des CSV.

**Étape 4.2 — Campagnes de mesure (E5, avec E1 et E3).** Trois configurations A, B et C ; au moins 10 répétitions ; 3 tailles de modèle ; provenance sur 1, 5, 10 et 20 rounds ; mesure de la croissance du registre. Consigner machine et versions.

**Étape 4.3 — Détection et faux refus (E4).** Lancer des centaines de falsifications automatiques (poids, explications, substitutions de modèle) et des diagnostics légitimes ; calculer taux de détection et taux de faux refus.

**Étape 4.4 — Analyse (E5).** Médiane et écart interquartile, tableau comparatif A/B/C, graphiques (volume écrit par taille de modèle, surcoût par round). Discuter honnêtement les limites. *Validation* : jalon J4, relevé complet.

## Phase 5 — Clôture (semaines 13–14)

**Étape 5.1 — Documentation (E3).** Guide d’installation, guide d’exploitation, description des API (OpenAPI), commandes de démonstration.

**Étape 5.2 — Rapport final (tous).** Plan : contexte, problématique, état de l’art succinct, choix technologique (note), architecture, réalisation, scénarios, mesures, limites, conclusion.

**Étape 5.3 — Répétition de la démonstration (tous).** Dérouler les cinq scénarios deux fois de suite sur la machine de présentation, avec une vidéo de secours enregistrée.

**Étape 5.4 — Gel et livraison (E3).** Étiquette de version Git, archive des livrables, vérification de la liste du §16. *Validation* : jalon J5.

# 14. Environnement, installation et exécution

**Poste de référence.** Linux ou WSL2, 4 cœurs, 16 Go de RAM (8 Go de mémoire minimum pour Docker), 30 Go de disque, aucun GPU.

**Outils à installer.** Docker et Docker Compose, Git, Go, Node.js (version LTS), Python 3 avec environnement virtuel, binaires et images Hyperledger Fabric. Figer les versions dans un fichier `versions.md` dès la semaine 1 et ne plus les changer.

**Paquets Python principaux.** flwr, torch, numpy, scikit-learn, opacus, captum, fastapi, uvicorn, pydantic, httpx, minio, psycopg, pytest, ruff, mypy, pandas, matplotlib.

**Fabric (principe).** Récupérer le script officiel d’installation de Fabric (`install-fabric.sh`) et télécharger les images Docker, les binaires et les exemples ; lancer le réseau de test (`network.sh up createChannel -ca`) puis déployer le chaincode (`network.sh deployCC` avec le langage Go). Les commandes exactes dépendent de la version retenue : suivre la documentation officielle correspondante.

**Exécution.** Une commande démarre l’infrastructure (Docker Compose, réseau Fabric), une commande lance la fédération, une commande lance les cinq scénarios, une commande exporte les mesures. Toutes sont décrites dans le guide d’exploitation.

**Convention de qualité.** Pull request et relecture obligatoires, tests unitaires pour chaque module, tests d’intégration par scénario, intégration continue, messages de commit clairs, aucune clé ni certificat dans Git.

# 15. Organisation et planning

| Phase | Semaines | Contenu | Jalon |
|:---------|:------|:------------------------------|:---------------|
| 0. Cadrage | S1–S2 | étude comparative, note de choix, dépôt, Docker, interface LedgerClient, registre local | J0 : note de choix validée |
| 1. Noyau | S3–S5 | fédération Flower, stratégies, empreintes, agent v1, scénario nominal sur registre local | J1 : bout en bout sur registre local |
| 2. Registre réel | S6–S8 | réseau Fabric, chaincode, adaptateur FabricLedger, porte, service de provenance | J2 : scénario nominal sur Fabric |
| 3. Scénarios | S9–S10 | attaques, falsification, file de reprise, interface d’audit | J3 : cinq scénarios passent |
| 4. Mesures | S11–S12 | trois configurations, tailles de modèle, tableaux | J4 : relevé complet |
| 5. Clôture | S13–S14 | rapport, documentation, répétition de la démonstration, gel du code | J5 : livraison |

Répartition proposée (adaptable à 3 ou 4 personnes en regroupant) : 1 Fédération et attaques ; 2 Registre et contrat ; 3 Empreintes, pseudonymes, agent et file ; 4 Porte, provenance et scénarios ; 5 Interface et mesures. Méthode : sprints de deux semaines, revue de code par pull request, intégration continue, définition de « terminé » = code testé, documenté, démontré.

# 16. Livrables

Note de choix technologique ; code de la fédération et des stratégies ; module d’empreinte et de pseudonymisation avec tests de reproductibilité ; agent d’ancrage et file de reprise ; configuration du réseau et chaincode ; porte de certification et service de provenance ; interface d’audit ; tests des cinq scénarios ; relevé de mesures et tableau comparatif ; documentation (installation, exploitation), rapport final, démonstration.

# 17. Risques

| Réf. | Risque | Probabilité | Parade |
|:----|:-------------------------|:--------|:-------------------------------|
| R1 | Installation de Fabric plus lourde que prévu | élevée | registre local d’abord ; interface LedgerClient ; installation lancée dès S3 |
| R2 | Multi-Krum exige n ≥ 2f + 3 : avec 3 cliniques, aucune tolérance à une clinique malveillante | certaine | démonstration d’attaque à 5 cliniques (ou filtre médiane/cosinus) ; scénario nominal à 3 |
| R3 | Empreintes non reproductibles (ordre, types, −0,0) | moyenne | format canonique, tests multi-processus dès la semaine 3 |
| R4 | Changements d’API de Flower ou de Fabric | moyenne | versions figées, aucune mise à jour en cours de projet |
| R5 | Jeu de données inadapté ou licence floue | moyenne | données synthétiques en secours, déclarées comme telles |
| R6 | Machine trop chargée (≈ 15 conteneurs) | moyenne | un pair par organisation, LevelDB, profils Compose légers |
| R7 | Dérive du périmètre (extensions) | moyenne | extensions C uniquement après J4 |
| R8 | Fort déséquilibre de charge dans l’équipe | faible | interfaces stables, revue croisée |

# 18. Limites et extensions

La fédération est simulée et les données découpées artificiellement ; la chaîne prouve la cohérence du processus, pas la qualité médicale du modèle. Extensions : signature par les cliniques, révocation tracée, ancrage d’une racine de Merkle sur un registre public, détection de dérive lors des réentraînements, comptabilisation formelle du budget de confidentialité.

# Glossaire

| Terme | Définition |
|:----------|:------------------------------------------------------|
| Apprentissage fédéré | entraînement d’un modèle commun par plusieurs sites qui n’échangent que des mises à jour de paramètres |
| Round | un cycle : entraînement local, envoi, agrégation, publication du modèle global |
| Empreinte | résumé cryptographique (SHA-256) d’un objet ; deux objets différents donnent des empreintes différentes |
| Ancrage | écriture d’une empreinte et de ses métadonnées sur le registre |
| Registre / chaîne permissionnée | registre distribué dont les écrivains sont des organisations identifiées |
| Contrat intelligent (chaincode) | programme exécuté par le registre qui valide et enregistre les écritures |
| Porte de certification | contrôle qui interdit d’utiliser un modèle dont l’empreinte n’est pas ancrée |
| Provenance | chaîne complète reliant une décision à son modèle, aux rounds et aux contributions |
| Non-répudiation | impossibilité pour un auteur de nier une contribution ancrée |
| Agrégation robuste | méthode (ex. Multi-Krum) qui écarte les contributions aberrantes |
| Pseudonyme | identifiant de substitution du patient, non réidentifiable sans la clé hors chaîne |
| Outbox | file persistante des ancrages à envoyer, rejouée en cas d’échec |
| Idempotence | rejouer la même opération ne produit pas de doublon |

# Annexe — structure proposée du dépôt

federation/ (serveur, clients, stratégies) · fingerprint/ (empreinte, pseudonymes, tests) · anchoring/ (agent, outbox, LedgerClient, adaptateurs) · chaincode/ (Go) · gateway/ (TypeScript) · services/ (porte, provenance, FastAPI) · ui/ (React) · infra/ (Compose, réseau Fabric) · scenarios/ (tests de bout en bout) · measures/ (scripts, notebooks, CSV) · docs/ (ADR, rapport)
