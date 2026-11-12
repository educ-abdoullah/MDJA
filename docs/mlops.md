# TD5 — thèmes, embeddings et suivi des exécutions

État du 12 novembre 2026. Le pipeline utilise un seul modèle local sur CPU et
un seul algorithme de regroupement en production. Aucun texte n'est envoyé à une API.

## 1. Choix et alternatives

- Modèle : `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`,
  révision **`e8f8c211226b894fcb81acc59f3b34ba3efd5f42`**, ONNX non quantifié.
  Ce modèle multilingue couvre le français. L'exécution utilise ONNX Runtime,
  sans PyTorch, sans GPU et sans fine-tuning. Une API aurait demandé une clé,
  une gestion des coûts et l'envoi des textes ; elle n'a pas été retenue.
- Entrée : titre suivi d'un retour à la ligne et du résumé propre. Tokenisation
  limitée aux **128 tokens du modèle** : un résumé long peut être tronqué, même si
  sa limite éditoriale est 500 caractères. Mean pooling des tokens avec masque
  d'attention, puis normalisation L2 ; **384 dimensions**. Deux threads et lots de 16.
- Regroupement : **HDBSCAN**, distance cosinus, calcul `brute`, `min_cluster_size=3`,
  `min_samples=2`, sélection `eom`, pas de groupe unique forcé. Il trouve le nombre
  de groupes et accepte le bruit, conformément aux choix de l'équipe. Pas d'UMAP.
- Nommage : TF-IDF sur les textes, contraste moyenne du groupe moins moyenne
  du reste du corpus, cinq mots/expressions, dont trois pour le nom. Aucun LLM.
  Les noms sont des mots-clés de travail, pas des titres rédactionnels validés.
- Suivi : PostgreSQL existant et artefacts JSON/NumPy ; MLflow serait utile pour
  une interface d'expériences plus riche, mais ajouterait un service à ce stade.

Toutes les versions directes ML sont figées dans `requirements-ml.txt`, alignées
sur Airflow. Les versions effectivement utilisées sont enregistrées dans chaque run.

Sources techniques : [fiche du modèle](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2)
et [documentation HDBSCAN scikit-learn](https://scikit-learn.org/stable/modules/generated/sklearn.cluster.HDBSCAN.html).

## 2. Démonstration des trois approches

`bin/compare_clustering.py` a été exécuté sur les **mêmes 130 articles et vecteurs réels**
du premier run. Ces essais sont une démonstration hors production, pas trois
algorithmes exécutés à chaque passage.

| Approche | Paramètres de démonstration | Groupes | Bruit | Silhouette |
|---|---|---:|---:|---:|
| K-means | k=8, seed=42, n_init=10 | 8 | 0 | 0,067 |
| Hiérarchique agglomératif | liaison moyenne, cosinus, seuil 0,45 | 88 | 0 | 0,21 environ |
| HDBSCAN retenu | paramètres du YAML | 14 | 67 | 0,321 |

K-means impose huit groupes et force chaque article à en rejoindre un.
Le seuil hiérarchique produit ici beaucoup de petits groupes, dont des singletons.
HDBSCAN correspond mieux au choix de conserver les articles isolés hors des thèmes.
**Les silhouettes ne sont pas directement comparables** : celle de HDBSCAN exclut
les 67 articles de bruit, contrairement aux deux autres approches.
Les sorties détaillées figurent dans `comparison-demo.json` du dossier du premier run.

## 3. Fenêtre, cache et reproductibilité

Le pipeline lit `articles_propres` avec une publication comprise entre
`cutoff - 24 h` et `cutoff`, bornes incluses, triée par identifiant brut.
Les dates nulles, anciennes et futures sont exclues. Airflow fournit son
`data_interval_end` comme cutoff ; ce n'est pas une sélection sur la date de récupération.

Le hash d'entrée SHA-256 couvre la liste ordonnée complète des instantanés.
`run_articles` conserve ces instantanés et leurs références aux bruts. Le recalcul
TD4 peut supprimer/réinsérer les propres sans casser les thèmes historiques :
aucune affectation ne référence directement la table propre volatile.

Le cache `embeddings` est indexé par hash du texte et de la configuration embedding,
qui inclut modèle, révision immuable et prétraitement. Une modification du texte,
de la révision ou du prétraitement entraîne une nouvelle entrée. Une forme incorrecte,
un vecteur nul ou non fini fait échouer le traitement. Les textes identiques sont
calculés une seule fois même s'ils appartiennent à plusieurs sources.

Le téléchargement initial du modèle remplit `data/huggingface/`, partagé entre
l'application et Airflow. Il nécessite Internet ; les passages suivants réutilisent
les fichiers locaux et le cache PostgreSQL. Les modèles ne sont pas embarqués dans Git.

Le run stocke versions de bibliothèques, version Python et empreinte du code MLOps.
Les empreintes des fichiers ONNX/tokenizer sont enregistrées lors d'un calcul.
Un changement de plateforme ou de versions peut produire de petites différences
numériques : il faut comparer aussi ces informations lors d'un rejeu.

## 4. Tables et artefacts

Migration : `infra/migrations/003_mlops.sql`, sans modification des migrations 001/002.

| Table | Rôle |
|---|---|
| `runs` | UUID, run Airflow, dates, statut, fenêtre, nombre/hash d'entrée, modèle/révision, paramètres, logiciels, métriques, artefacts, erreur |
| `embeddings` | Cache de vecteurs versionné par texte et modèle |
| `run_articles` | Articles exacts utilisés par un run, sous forme d'instantanés |
| `themes` | `run_id`, label, nom, mots-clés, taille |
| `articles_themes` | Affectation par article et run ; label NULL pour le bruit |

Un run ne remplace pas les anciens thèmes. Les consommateurs doivent choisir
explicitement le dernier **run réussi**, et non mélanger les lignes de plusieurs runs.

Chaque dossier `data/mlops/<uuid>/` contient :

- `input.json`, `parameters.json`, `software.json` ;
- `vectors.npy`, dans le même ordre que `input.json` ;
- `themes.json`, `assignments.json`, `metrics.json` ;
- `manifest.json`, avec UUID, hash d'entrée et SHA-256 de chaque artefact principal.

`comparison-demo.json` est une analyse pédagogique ajoutée séparément, hors manifeste.
Les métriques sont nombre de thèmes, taille médiane, nombre/part de bruit,
silhouette cosinus sur les articles affectés et compteurs du cache. La silhouette
vaut `null`, avec une raison, quand elle n'est pas définie. Un lot vide ou trop petit
est tracé sans forcer la création de thèmes.

## 5. Orchestration et erreurs

Chaîne du DAG `gazette_daily` :

```text
collect_rss → process_quality → generate_quality_report → check_quality → cluster_themes
```

Le regroupement ne démarre que si les contrôles qualité réussissent. Il tourne
après chaque cycle de 30 minutes, donc aussi chaque jour. `max_active_runs=1`
évite le chevauchement des runs Airflow. La tâche MLOps est bornée à dix minutes ;
le timeout global passe à quarante minutes pour inclure le premier chargement.
Un passage exceptionnellement long peut retarder le suivant, sans en exécuter deux ensemble.

Un verrou de session PostgreSQL sérialise aussi les exécutions CLI/MLOps.
La copie des entrées partage le verrou du nettoyage TD4. Thèmes et affectations
sont publiés dans une transaction avec le passage du run à `success`.
Une exception laisse un run `failed`, une erreur et ses données déjà tracées ;
les caches déjà calculés restent réutilisables. Des fichiers d'un run échoué peuvent
rester sur disque mais ne sont pas publiés comme résultat réussi.
Un arrêt brutal peut laisser `running` : à examiner avec l'état de la tâche Airflow,
sans le considérer comme un succès. Pas de récupération automatique de ces runs à ce stade.

Relancer la même tâche pour un run Airflow déjà réussi réutilise son UUID MLOps.
Le rejeu explicite ci-dessous crée au contraire une nouvelle expérience, liée à
l'ancienne par `parameters.replay_of` et le manifeste.

## 6. Où regarder et commandes

Depuis la racine, avec Docker démarré :

```powershell
docker compose build app airflow-init
docker compose run --rm gazette-init
docker compose run --rm --build storage-tests
docker compose up -d --wait airflow-api-server airflow-scheduler airflow-dag-processor
```

Dans [Airflow](http://localhost:8081), ouvrir `gazette_daily`, puis `cluster_themes`.
Le log `gazette_mlops_run` et le XCom donnent l'UUID et les métriques.

Pour un essai explicite hors planification :

```powershell
docker compose run --rm --no-deps --entrypoint python app -m gazette.mlops --cutoff 2026-11-12T12:52:43.397787+00:00
```

Un cutoff identique ne suffit pas à figer une base qui évolue. Pour reproduire
les données et paramètres exacts d'un run réussi, utiliser ses instantanés :

```powershell
docker compose exec -T airflow-dag-processor python -m gazette.mlops --replay def36fbf-26a3-48cc-b072-ffc2c51ced19
```

Le rejeu vérifie le hash des instantanés et conserve sa propre version du code/logiciels.
Il ne réécrit ni les articles propres ni les thèmes du run original.

Requêtes consultables avec `docker compose exec -T postgres psql -U airflow -d gazette` :

```sql
SELECT id, airflow_run_id, status, window_start, window_end,
       input_count, input_hash, metrics FROM runs ORDER BY started_at DESC;

SELECT nom, mots_cles, taille FROM themes
WHERE run_id=(SELECT id FROM runs WHERE status='success' ORDER BY started_at DESC LIMIT 1)
ORDER BY taille DESC, label;

SELECT a.label, r.snapshot->>'titre' AS titre, r.snapshot->>'source' AS source
FROM articles_themes a JOIN run_articles r USING(run_id,article_brut_id)
WHERE a.run_id='def36fbf-26a3-48cc-b072-ffc2c51ced19'
ORDER BY a.label NULLS LAST, a.article_brut_id;
```

## 7. Thèmes du jour et preuves du 12 novembre

### Dernier passage automatique vérifié : 14 h, heure de Paris

Run Airflow **`scheduled__2026-11-12T13:00:00+00:00`**, cinq tâches réussies.
Run MLOps **`79f97bf3-b39e-416f-b933-343e28417b8c`**, statut `success` en base :
**141 articles, 15 thèmes, 72 articles affectés, 69 isolés (48,94 %), taille médiane
4 et silhouette 0,2922**. Le cache a fourni 140 vecteurs ; un seul texte a été calculé.
Ce run est bien lancé par le scheduler après le nettoyage et les contrôles.

Les noms et tailles exacts sont dans [themes.json](../data/mlops/79f97bf3-b39e-416f-b933-343e28417b8c/themes.json),
les articles dans [input.json](../data/mlops/79f97bf3-b39e-416f-b933-343e28417b8c/input.json)
et les affectations dans [assignments.json](../data/mlops/79f97bf3-b39e-416f-b933-343e28417b8c/assignments.json).
Ces fichiers sont locaux, hors Git ; les lignes correspondantes sont conservées en base.
Ce passage ajoute notamment un groupe de trois articles nommé automatiquement
« issus / coordination / coordination gilets ». Les labels sont propres à chaque
run et ne sont pas des identifiants de thèmes stables d'une journée à l'autre.

### Premier passage et démonstration reproductible

Premier run réel : **`def36fbf-26a3-48cc-b072-ffc2c51ced19`**, exécuté par la cinquième
tâche d'un run Airflow complet, pas par un script de regroupement isolé.
Run Airflow : `manual__2026-11-12T12:52:43.526782+00:00` ; cinq tâches réussies.
Fenêtre : du 11 novembre 12:52:43 au 12 novembre 12:52:43 UTC.
Hash d'entrée : `f2d380c5207627ec701518e7fee6af45ad75e5a7e0dd7c5a6c58dc9718fff2e6`.

**130 articles, 14 thèmes, 63 articles affectés, 67 isolés (51,54 %), taille médiane
3,5 et silhouette 0,3208.** Le bruit reste stocké et traçable.

| Label | Nom automatique | Taille |
|---:|---|---:|
| 0 | immeuble / new / new york | 3 |
| 1 | cop / gaz / antalya | 3 |
| 2 | plan / agriculture / plan relance | 3 |
| 3 | riches / contribution / express | 3 |
| 4 | liquidation / liquidation judiciaire / excellence | 3 |
| 5 | colom / noir / scott | 3 |
| 6 | écoles / bombe / lycées | 5 |
| 7 | émissaires / ukraine / russie | 7 |
| 8 | nvidia / chinoise / huang | 4 |
| 9 | israélienne / frappe / armée | 3 |
| 10 | maladie / santé / pays | 10 |
| 11 | présidentielle / candidats / publics | 5 |
| 12 | gauche / personnalités / extrême | 7 |
| 13 | edouard philippe / philippe / edouard | 4 |

Validation : Ruff réussi ; **87 tests réussis avec PostgreSQL**, aucun ignoré.
Tests de cache sur dix articles, fenêtre, vide/bruit, deux groupes contrôlés,
échec enregistré, réexécution Airflow, intégrité des artefacts et rejeu après
modification des propres. Les tests de CI emploient un encodeur contrôlé pour
tester la logique sans réseau ; le modèle réel a été vérifié séparément :
**dix vrais articles → matrice 10×384, puis dix hits cache sans chargement du modèle**.

Rejeu réel : **`981dc189-739e-4b94-96a5-507d3c3ea25e`**. Même hash d'entrée,
mêmes 14 thèmes, mêmes métriques ; **130 hits cache et zéro texte recalculé**.
Les journaux locaux sont dans `.validation/td5-model-test.log`, `td5-tests-final.log`,
`td5-airflow-run.log` et `td5-replay.log`, hors Git.

### Première lecture manuelle et matière pour le TD6

- Groupe 0 cohérent : trois médias décrivent l'effondrement d'un immeuble à New York.
  Les bilans humains diffèrent entre mises à jour ; cela ne doit pas créer trois thèmes.
- Groupe 7 partiellement cohérent : Ukraine/Russie, mais aussi une revue de presse
  multi-sujets et un article de commémorations. Hypothèse : le résumé multi-sujets
  et des proximités politiques générales créent un pont entre événements.
- Groupe 10 trop large : recherche et santé, vaccination, jeunesse/chômage/climat,
  accompagnement d'éleveurs. Hypothèse : les proximités générales ne correspondent
  pas forcément à un même événement ; les paramètres de densité et les extraits
  devront être évalués, pas simplement optimiser la silhouette.
- Noms parfois redondants : « new / new york » ou « philippe / edouard philippe ».
  Piste TD6 : supprimer les mots inclus dans une expression plus informative.

La lecture de **deux journées distinctes** reste à faire : nous n'avons pas
fabriqué les résultats d'une deuxième journée. Conserver les runs et noter ici
les observations de la prochaine journée, puis les hypothèses testées au TD6.

## 8. Rétention et limites

Conserver runs, instantanés et artefacts 90 jours pour cette phase du projet ;
les clés étrangères vers les bruts imposent une purge coordonnée des affectations,
thèmes, instantanés et runs avant suppression des index bruts concernés.
Le cache peut être purgé séparément : il est recalculable. Aucune purge automatique
n'est activée. Les artefacts restent locaux et hors Git, avec sauvegarde à prévoir.
Le schéma de suivi PostgreSQL est versionné, pas un registre de déploiement MLflow.
Le regroupement est une v1 à évaluer au TD6 ; 14 thèmes ne signifie pas 14 thèmes
éditorialement validés. Les sources HTTP en panne restent un problème de collecte
distinct ; la qualité des thèmes ne garantit pas la couverture de tous les médias.

## 9. Fichiers livrés

| Fichier | Fonction |
|---|---|
| `src/gazette/mlops/embeddings.py` | Modèle ONNX CPU, prétraitement, validation des vecteurs et cache PostgreSQL |
| `src/gazette/mlops/clustering.py` | HDBSCAN, noms discriminants et métriques |
| `src/gazette/mlops/pipeline.py` | Fenêtre, instantanés, historique, transactions, artefacts et rejeu |
| `src/gazette/mlops/__main__.py` | Commande CLI, cutoff explicite et `--replay` |
| `src/gazette/mlops/__init__.py` | Paquet Python du TD5 |
| `config/clustering.yaml` | Modèle/révision, prétraitement, paramètres de regroupement et mots exclus du nommage |
| `infra/migrations/003_mlops.sql` | Les cinq nouvelles tables et leurs contraintes |
| `requirements-ml.txt` | Dépendances CPU figées |
| `tests/test_mlops.py` | Tests de calcul contrôlé, cache, fenêtre, bruit, historique et erreurs |
| `bin/verify_mlops.py` | Vérification du modèle réel et de son cache sur dix articles propres |
| `bin/compare_clustering.py` | Démonstration des trois méthodes sur un même jeu réel |

Fichiers modifiés : `requirements.txt` et `pyproject.toml` (installation ML), les deux
Dockerfiles (dépendances et configuration), `docker-compose.yml` (cache modèle partagé,
configuration montée), `dags/gazette_daily.py` (cinquième tâche et timeout),
`.github/workflows/ci.yml` (contrôle du nouveau DAG), `README.md`, `CONTRIBUTING.md`,
`docs/donnees.md` et `docs/architecture.md` (fonctionnement actuel).
Les rapports TD4 quotidiens sont aussi actualisés par les passages du pipeline.
