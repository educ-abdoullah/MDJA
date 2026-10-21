# Dictionnaire des données — étape 2 : stockage brut

Version initiale du 21 octobre 2026. Le catalogue des huit sources est enregistré dans
la base PostgreSQL **gazette**, distincte de la base **airflow**. Les métadonnées des
articles sont écrites dans `articles_bruts/`. Le collecteur automatique sera raccordé
à ce stockage à l'étape 3 ; sa fréquence n'est pas modifiée à cette étape.

## 1. Catalogue fourni : sources.csv

Encodage UTF-8 et séparateur **point-virgule**, conformément au format demandé :

```text
Nom;type;region;source;acces;conditions;notes
```

| Colonne | Signification |
|---|---|
| Nom | Nom du média |
| type | Classification fournie par l'équipe, PQR ou PQN |
| region | Couverture géographique renseignée |
| source | URL exacte du flux RSS/Atom |
| acces | Note d'accès fournie par l'équipe |
| conditions | Notes de réutilisation fournies ; pas une validation juridique |
| notes | Notes libres du catalogue |

Les huit lignes sont prises en compte. Les accents illisibles du texte collé ont été
réparés ; les URL indiquées ont été conservées. `source` désigne ici le flux ; dans
un fichier d'article, `source` désigne l'identifiant stable du média.

Identifiants : `ouest-france`, `sud-ouest`, `la-provence`, `le-telegramme`, `franceinfo`,
`humanite`, `liberation`, `lemonde`. Ils sont calculés depuis le nom, sans accent et
avec deux alias explicites pour conserver `humanite` et `lemonde` déjà utilisés.
Le lecteur accepte aussi l'ancien format CSV pour conserver la compatibilité des tests.

## 2. Table sources dans PostgreSQL

| Champ | Type | Rôle |
|---|---|---|
| id | text, clé primaire | Identifiant stable, de 1 à 64 caractères ASCII autorisés |
| nom | text, unique | Nom du média |
| type | text | PQR ou PQN selon le catalogue |
| region | text | Couverture géographique |
| url_flux | text, unique | Adresse RSS/Atom |
| acces, conditions, notes | text | Informations du catalogue conservées |
| actif | boolean | Éligibilité à une future collecte ; true lors du premier import |
| derniere_reussite | timestamptz, nullable | Dernière collecte réussie, à alimenter à l'étape 3 |
| echecs_consecutifs | integer >= 0 | Compteur persistant, initialisé à zéro ; étape 4 |
| etag | text, nullable | Valeur de cache à réutiliser lors des futures requêtes |
| last_modified | text, nullable | En-tête HTTP original, conservé sans conversion forcée |
| sommeil_depuis | timestamptz, nullable | Date de mise en sommeil ; étape 4 |
| derniere_erreur | text, nullable | Motif du dernier échec ; étape 4 |

Un réimport met à jour les informations du catalogue mais **ne remet pas à zéro**
les compteurs, dates, caches ou l'état actif existants. Il ne supprime pas de source.
Cela évite de réveiller une source endormie au prochain démarrage.
À cette étape, zéro échec et une date nulle sont des valeurs d'initialisation :
ils ne prouvent pas qu'un cycle de collecte automatique a réussi.

## 3. Un fichier JSON par article

Emplacement : `articles_bruts/<source>/<id>.json`. Le dossier est suivi par un
`.gitkeep`, mais les articles générés sont exclus de Git et des contextes Docker.

| Champ JSON | Type | Rôle |
|---|---|---|
| id | string SHA-256, 64 caractères | Empreinte stable de source + séparateur nul + lien |
| source | string | Identifiant de sources.id |
| lien | string HTTP(S) | URL fournie, espaces extérieurs retirés ; maximum 2 048 octets UTF-8 |
| titre | string | Titre reçu, vide autorisé ; borne à 1 000 caractères |
| resume | string | description RSS ou summary Atom, éventuellement HTML ; borne à 2 000 caractères |
| publie_le | string ISO 8601 UTC ou null | published, sinon updated ; null si absent ou inexploitable |
| recupere_le | string ISO 8601 UTC | Heure d'ingestion de cette version du fichier |
| rubrique | liste de strings | Catégories reçues ; liste vide autorisée, maximum 20 valeurs de 200 caractères |
| payload | objet | Métadonnées d'origine explicitement sélectionnées |

`payload` conserve `guid_ou_id` (maximum 4 096 caractères), les dates originales,
le format du résumé et les indicateurs `titre_tronque` / `resume_tronque`.
Il ne copie pas l'objet feedparser entier. L'identifiant éditeur est conservé à titre
de provenance ; la clé anti-doublon ne repose pas uniquement sur lui.

Les éléments sans lien HTTP(S) exploitable ou avec un lien dépassant la borne sont
exclus car leur identité naturelle ne peut pas être indexée. L'extrait provient
explicitement de `description` ou `summary` : aucun repli sur `content:encoded` ou
le texte intégral Atom. Les images, pièces jointes et commentaires ne sont pas téléchargés.
Le HTML éventuel du résumé est stocké comme chaîne JSON et devra être échappé lors
d'un futur affichage. Ce format ne doit pas être injecté directement dans une page.

Contrairement à l'ancien parseur du TD 2, ce parseur brut **ne filtre pas la fraîcheur** :
dates anciennes, futures, absentes et titres vides sont conservés pour le TD qualité.
Ces valeurs ne deviennent pas pour autant admissibles dans une édition publiée.

## 4. Anti-doublon et reprise après interruption

La table `articles_bruts_index` contient `id`, `source`, `lien`, `chemin` relatif et
`recupere_le`. Une contrainte `UNIQUE(source, lien)` protège les écritures concurrentes.
Les liens sont conservés, y compris paramètres de requête et fragments : aucune
suppression de suivi implicite n'est faite à cette étape. Deux URL différentes
restent donc deux clés différentes, même si elles mènent au même contenu éditorial.

Déroulement d'une écriture :

1. Transaction PostgreSQL et verrou par source, dans un ordre stable.
2. Vérification du fichier et de l'index pour la clé source+lien.
3. Si le fichier existe avec une identité cohérente, conservation de la première version.
4. Sinon, écriture UTF-8 dans un fichier temporaire, flush/fsync et remplacement atomique.
5. Enregistrement de la clé unique et du chemin, puis commit PostgreSQL.

La base et le système de fichiers ne forment pas une transaction distribuée.
Si l'exécution s'arrête après le fichier mais avant le commit, le passage suivant
reconnaît le fichier et répare son index. Si un fichier indexé manque ou est illisible,
une nouvelle réception de l'item permet de le réécrire et compte une réparation.
Cette réparation utilise l'item de la nouvelle réception, pas une sauvegarde historique.

Les compteurs de cette primitive de stockage sont `recus`, `ecrits`, `ignores`,
`repares`. Ils servent à vérifier le stockage ; le bilan complet par source, les
compteurs d'erreurs et les requêtes conditionnelles appartiennent aux étapes suivantes.

## 5. Migration et initialisation

`infra/migrations/001_sources_articles.sql` crée les deux tables. Le moteur enregistre
chaque migration dans `schema_migrations` avec version, empreinte et date d'application.
Une migration déjà appliquée est ignorée ; si son contenu change, l'initialisation
échoue. Les migrations sont transactionnelles et les fins de ligne sont normalisées.

Le service `gazette-init` crée la base métier si nécessaire, applique les migrations
et importe les huit sources. Les connexions restent sur le réseau Docker ; le mot
de passe existant est injecté depuis `.env`, sans ajout de secret dans Git.

```powershell
docker compose build app
docker compose run --rm gazette-init
docker compose run --rm --entrypoint python app -m gazette.storage --list-sources
```

Pour importer manuellement un exemple enregistré :

```powershell
docker compose run --rm --entrypoint python app -m gazette.storage --input fixtures/lemonde_sample_rss.xml --source lemonde
```

Refaire cette commande ne crée pas un second fichier pour le même lien.
Les scripts `bin/dev` et `bin/dev.ps1` exécutent l'initialisation métier au démarrage.
La commande habituelle `app` reste une démonstration de l'ancien collecteur Le Monde
vers `data/raw/` ; l'intégration automatique à `articles_bruts/` attend l'étape 3.

## 6. Validation et choix techniques

- PostgreSQL existant : transactions, contraintes uniques et verrous ; SQLite demanderait
  une organisation différente des accès entre conteneurs, et JSON seul ne suffit pas
  à partager correctement l'état des sources et les clés concurrentes.
- Migrations SQL versionnées : simples pour ce premier schéma. Alembic serait utile
  pour un historique plus riche et des modèles ORM ; il n'est pas nécessaire ici.
- Pilote psycopg2-binary 2.9.13 : aligné sur les contraintes de notre image Airflow,
  sans compilateur local. Psycopg 3 est une alternative, mais ajouterait un autre pilote.
- JSON par item : exigé par la séance, inspectable et indépendant des versions du parseur.
  CSV représente moins bien les champs facultatifs, listes et objets de provenance.

```powershell
docker compose run --rm --build storage-tests
```

Ces tests utilisent le vrai PostgreSQL, dans des schémas temporaires dédiés, sans
effacer les sources ni articles métier. Ils couvrent réimport, deux passages sans
doublon, écritures concurrentes, réparation d'index et fichier manquant.
Sans TEST_DATABASE_URL, les tests PostgreSQL sont explicitement ignorés ; les tests
unitaires restent exécutables hors base. La CI lance aussi la suite avec PostgreSQL.

### Résultat local du 21 octobre 2026

- Migration 001 appliquée, huit sources présentes dans la base métier.
- Six exemples réels importés : six JSON et six clés indexées.
- Second passage des mêmes exemples : zéro nouvelle écriture, six éléments ignorés.
- 33 tests réussis dans le conteneur avec PostgreSQL, Ruff réussi.
- Import du DAG et lecture des huit sources vérifiés dans l'image Airflow.
- Les deux flux inaccessibles restent au catalogue sans article fabriqué.
- Les compteurs de sources sont initialisés, pas encore alimentés automatiquement.
