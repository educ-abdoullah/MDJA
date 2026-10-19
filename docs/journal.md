---
noteId: "b7944300cba711f1a85549129aad7d1c"
tags: []

---

# Journal de bord

## 19 octobre 2026 — Passage à Apache Airflow

- Constat : arborescence créée, anciennes configurations supprimées, cadrage encore basé sur systemd.
- Décision : Airflow 3.3.2 avec LocalExecutor, PostgreSQL et Docker Compose.
- Mise en place : API, scheduler, processeur de DAG, migration de base, volumes persistants,
  secrets locaux générés, premier DAG RSS à 6 h Europe/Paris, retries par source.
- Périmètre : archives JSON uniquement ; aucune édition publiée à ce stade.
- Vérifications : 13 tests unitaires réussis, Ruff réussi, configuration Compose valide,
  construction réussie et import du DAG sans erreur avec Airflow 3.3.2.
- Incident local : Docker Desktop était arrêté ; démarré pour la validation.
  La politique PowerShell bloque les scripts ; exécution ponctuelle autorisée pour
  `bin/dev.ps1`, sans modification permanente de la politique du poste.
- Incident de construction : Compose 5 lançait plusieurs constructions avec le même
  nom d'image, provoquant une collision lors de l'export. Correction : une seule
  définition `build`, sur `airflow-init` ; les autres services réutilisent l'image.
  Reconstruction réussie après correction.
- Adaptation Airflow 3.3 : suppression de l'ancien argument `include_examples`
  dans le contrôle `DagBag` de la CI ; import local vérifié avec les deux tâches attendues.
- Port 8080 déjà occupé : utilisation du port local 8081, configurable via `AIRFLOW_PORT`.
- Résultat : base, API, scheduler et processeur de DAG sains. `gazette_daily` activé
  sur cette instance. Deux runs réussis (premier run planifié et `validation_initiale`),
  chacun avec 16 articles Le Monde archivés dans un dossier distinct sous `data/raw`.
  La CI est écrite mais n'a pas encore été exécutée sur GitHub.

## 19 octobre 2026 — Mise en conformité du livrable TD 2

- Catalogue : huit médias conservés avec les conditions et notes saisies par l'équipe,
  conversion UTF-8, colonnes explicites pour le site et le flux, Le Monde seul actif.
  Le site de Sud Ouest a été corrigé ; les sept autres flux restent à vérifier.
- Arborescence : `docs/` en minuscules et nouveau dossier `infra/`.
- Application : CLI `python -m gazette`, Dockerfile multi-étapes avec cibles app/test,
  image finale mesurée à environ 44 Mo, UID 10001 non root vérifié.
  Airflow conserve sa propre image dans `infra/airflow/Dockerfile`.
- Démarrage : scripts POSIX `bin/dev`, `bin/test`, variantes PowerShell et génération
  des secrets depuis Docker ; aucun Python requis sur le poste pour lancer et tester.
- Tests : 15 cas réussis sur Windows et dans le conteneur Linux, lint réussi.
  Ajout d'un test du catalogue réel et d'une collecte CLI complète via HTTP local.
- Preuve rouge/verte locale : fixture volontairement cassée dans un clone isolé,
  code de retour 1, puis fixture restaurée et code 0 avec 15 tests réussis.
  Preuves locales dans `.validation/20261019T123757/red.log`, `green.log`, `red-green.json`.
  Ces preuves locales ne constituent pas une exécution de GitHub Actions.
- Clone propre : instantané Git local puis clone sans `.env`, `.venv`, logs ni données.
  Le premier essai a révélé un défaut de droits sur les dossiers créés par Docker
  sous Windows. Correction du bootstrap : propriétaire AIRFLOW_UID et groupe 0,
  droits 0770 sur les seuls dossiers de travail. Relance réussie avec 15 articles.
  Second clone entièrement vierge validé sans modification manuelle : services sains
  et 15 articles produits sous `data/raw/81aa1fe45316f16ceb039550/lemonde.json`.
  Instantané local de code : `aa06622b2a878a5c7623f7b0ab80ea6d9016ed1a` (hors dépôt distant).
- CI écrite : jobs dépendants lint → tests → build et smoke Airflow → push GHCR.
  Transfert de l'image vérifiée entre jobs, tags UTC+SHA court et SHA complet,
  authentification GITHUB_TOKEN limitée au job push. Pas de push depuis une pull request.
- Documentation : README avec deux commandes de lancement, contribution, stratégie
  CI/CD en dix lignes et fiche de revue croisée à remplir.
- Limites : accès réseau GitHub non autorisé lors de la vérification et connecteur
  GitHub non connecté. Aucun push de code, publication GHCR, lien de CI rouge/verte
  ou revue croisée avec une autre équipe n'est revendiqué à ce stade.
