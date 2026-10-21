---
noteId: "8f1c2450cba311f1a85549129aad7d1c"
tags: []
---

# La Gazette MDJA

Premier livrable : lire une source RSS, filtrer ses métadonnées et produire du JSON.
Le collecteur fonctionne seul dans une petite image Docker ; Airflow 3.3.2 orchestre
sa collecte quotidienne à 6 h Europe/Paris. PostgreSQL conserve les métadonnées Airflow.

## Cloner et lancer en deux commandes

Prérequis : Git, Docker avec conteneurs Linux, Compose v2 récent et au moins 4 Go
de mémoire pour Docker (8 Go conseillés). Aucun Python ni PowerShell sous Linux requis.

Linux / macOS :

```sh
git clone https://github.com/educ-abdoullah/MDJA.git MDJA
sh MDJA/bin/dev
```

Windows, depuis PowerShell :

```powershell
git clone https://github.com/educ-abdoullah/MDJA.git MDJA
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\MDJA\bin\dev.ps1
```

L'option PowerShell concerne uniquement ce processus ; aucune politique permanente
n'est modifiée. Ces commandes concernent la version une fois publiée sur le dépôt distant.

Le script construit les images, génère `.env` sans écraser les secrets existants,
initialise PostgreSQL/Airflow, attend les services et effectue une première collecte.
Le fichier JSON apparaît dans `MDJA/data/raw/<empreinte-du-run>/lemonde.json`.
Un échec réseau fait échouer la commande et reste visible.

Airflow : [localhost:8081](http://localhost:8081), utilisateur `admin`.
Depuis le dossier du projet, lire son mot de passe généré :

```sh
docker compose exec airflow-api-server cat /opt/airflow/auth/passwords.json
```

Le port 8081 peut être changé avec `AIRFLOW_PORT` dans `.env`. Le DAG est créé en pause
sur une nouvelle installation. Pour activer le planning et lancer un run manuel :

```sh
docker compose exec airflow-scheduler airflow dags unpause gazette_daily
docker compose exec airflow-scheduler airflow dags trigger gazette_daily
```

## Tester

Depuis la racine du dépôt, uniquement avec Docker :

```sh
sh bin/test
```

Sous Windows :

```powershell
powershell.exe -NoProfile -ExecutionPolicy Bypass -File .\bin\test.ps1
```

Ces commandes construisent la cible Docker `test`, exécutent Ruff puis pytest et
renvoient un code non nul au premier échec. Les fixtures et le serveur HTTP local de
test rendent les vérifications indépendantes des journaux. Elles incluent le catalogue
réel du dépôt et une collecte complète en ligne de commande vers un JSON.

Pour développer en Python : créer un environnement Python 3.12, installer
`requirements-dev.txt`, puis exécuter `python infra/check.py`.

## Sources et archives

`sources.csv` conserve huit médias, leurs régions et les conditions renseignées par
l'équipe. Il est encodé en UTF-8, séparé par des points-virgules, avec les colonnes :
`Nom;type;region;source;acces;conditions;notes`.
`source` contient le véritable flux RSS/Atom. Les huit médias sont pris en compte.
Le diagnostic du 21 octobre constate six flux lisibles, une boucle de redirection
pour Sud Ouest et un refus 403 pour Le Télégramme. Les URL demandées sont conservées.
Les conditions conservées sont des notes de l'équipe, pas une validation juridique.

Le parseur garde les titres/liens datés de moins de 24 h à la collecte, rejette les
dates futures et les doublons d'URL dans un flux. Il ne télécharge pas les articles
intégraux. Timeout réseau : 30 s ; taille maximale : 5 Mio. Une reprise du même run
remplace atomiquement son archive ; un nouveau run conserve une autre archive.

Pour relancer la collecte seule :

```sh
docker compose run --rm --no-deps app
```

## Stockage brut — étape 2

Le démarrage initialise aussi la base métier `gazette`, distincte de `airflow`, avec
une table `sources` et un index unique `(source, lien)`. Le nouveau stockage produit
un JSON par article sous `articles_bruts/`, sans filtre de fraîcheur. Il conserve
les métadonnées bornées, pas le texte intégral. Le raccordement du collecteur à ce
stockage et le cycle de 30 minutes restent les prochaines étapes.

```powershell
docker compose run --rm gazette-init
docker compose run --rm --entrypoint python app -m gazette.storage --list-sources
docker compose run --rm --entrypoint python app -m gazette.storage --input fixtures/lemonde_sample_rss.xml --source lemonde
docker compose run --rm --build storage-tests
```

Le service `app` utilise Le Monde par défaut pour préserver la démonstration initiale.
Les champs, migrations, reprises après interruption et limites sont expliqués dans
[docs/donnees.md](docs/donnees.md). La CI exécute les tests du vrai PostgreSQL.

## Images et CI

Le DAG prévoit au maximum 12 tentatives par tâche : la première, 3 retries sans délai
volontaire, puis jusqu'à 8 retries espacés de 30 minutes. Chaque tentative est limitée
à 3 minutes et le DAG à 10 h, pour laisser les deux étapes successives utiliser leurs
reprises. Un succès arrête les retries ; les logs indiquent le numéro et le délai choisi.

Le `Dockerfile` principal contient les étapes `dependencies`, `runtime`, `test`, `app`.
L'image finale ne contient ni Airflow, ni les outils de tests, ni les fichiers de build.
Elle utilise un utilisateur non root. L'image d'orchestration Airflow est définie dans
`infra/airflow/Dockerfile` et réutilisée par les services Airflow.

GitHub Actions enchaîne **lint → tests → build et vérification Airflow → push GHCR**.
Le push est exécuté uniquement sur un événement push, après réussite des étapes
précédentes ; une pull request construit et teste sans publier d'image.
L'image vérifiée est transférée entre jobs et publiée sous `ghcr.io/educ-abdoullah/mdja`
avec les tags `YYYYMMDDTHHMMSSZ-<sha12>` et `sha-<sha-complet>`.
L'authentification utilise le `GITHUB_TOKEN` du job avec `packages: write`.
Les résultats effectifs et les liens de preuve sont consignés dans `docs/Archive/journal.md`.

## Exploitation et contribution

`docker compose stop` arrête les services ; `docker compose down` retire les conteneurs
en conservant les volumes. Garder `.env` et les volumes pour conserver la base et
les identifiants. Données et logs restent hors Git. Le poste et Docker doivent rester
actifs pour les exécutions quotidiennes. `GAZETTE_SKIP_COLLECT=1` permet à la CI de
vérifier la stack sans joindre les médias.

Voir [CONTRIBUTING.md](CONTRIBUTING.md), [stratégie CI/CD](docs/Archive/ci-cd.md),
[cadrage](docs/cadrage.md), [architecture](docs/architecture.md),
[journal](docs/Archive/journal.md), [données](docs/donnees.md)
et [fiche de revue croisée](docs/Archive/revue-croisee.md).

Le raccordement de la collecte au stockage brut, les reprises par source, le cycle
de 30 minutes, les thèmes, synthèses et publication à 7 h restent les étapes suivantes.
