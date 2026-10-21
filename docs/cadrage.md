# La Gazette MDJA — Cadrage du projet

**Document :** `docs/cadrage.md`  
**Statut :** cadrage initial — décisions techniques retenues, points à confirmer  
**Date :** 19 octobre 2026

## 1. Besoin reformulé

Nous voulons construire une **gazette de presse quotidienne automatique**. Le système récupère des informations issues de la presse nationale et régionale, détecte les principaux sujets du jour et publie une édition contenant, pour chaque thème, les sources et des liens pour lire la suite.

Le projet ne doit pas seulement fonctionner sur le poste d'un membre du groupe : il doit **tourner sans intervention humaine**, disposer d'un historique d'exécution et permettre de comprendre puis corriger les incidents. Nous devons être capables de prouver si l'édition attendue a bien été publiée.

### Critères de réussite

- **Une édition par jour**, disponible **à 7 h** (heure locale `Europe/Paris`).
- Les articles de l'édition ont **moins de 24 h** à la publication, lorsque leur date est vérifiable.
- L'édition indique les **thèmes, titres/extraits autorisés, sources, dates et liens** vers les articles.
- Les doublons sont traités, les erreurs sont journalisées, les exécutions sont identifiables.
- Les traitements sont **automatisés, relançables, reproductibles et documentés**.
- Les incidents et correctifs sont consignés dans `docs/journal.md` au fil du projet.

## 2. Périmètre

### Inclus

1. Sélection et suivi de sources nationales et régionales dans `sources.csv` (URL, méthode d'accès, conditions de réutilisation, statut).
2. Collecte quotidienne des **métadonnées accessibles et autorisées** : titre, court extrait fourni par la source, URL, date, nom de l'éditeur et identifiant éventuel.
3. Archivage des réponses brutes autorisées et stockage des données normalisées.
4. Contrôles de qualité : champs nécessaires, fraîcheur, déduplication, cohérence des dates.
5. Regroupement des articles par thèmes et restitution lisible.
6. Génération, publication et archivage d'une édition quotidienne.
7. Planification, relance contrôlée, logs structurés, alertes de non-publication et documentation technique.
8. Déploiement reproductible à partir de fichiers de configuration versionnés dans Git.

### Exclus

- Collecte ou redistribution du **texte intégral** des articles.
- Collecte des **images, commentaires, profils et données personnelles**.
- Contournement d'abonnements, paywalls, authentifications, CAPTCHA ou restrictions techniques.
- Scraping massif ou collecte contraire aux conditions des éditeurs.
- Application mobile, personnalisation individuelle des éditions et analyse des comportements des lecteurs.
- Achat d'API ou d'hébergement payant pour le prototype.

## 3. Contraintes et hypothèses

| Contrainte | Conséquence pour notre conception |
|---|---|
| Publication à **7 h**, une fois par jour | Déclenchement en amont ; contrôle de fin de traitement ; édition unique par date |
| Fraîcheur **< 24 h** | Comparaison avec l'heure de publication, stockage des dates et des fuseaux horaires |
| **Budget zéro** | Priorité aux logiciels libres et à une machine déjà disponible |
| Respect des éditeurs | Inventaire des conditions dans `sources.csv`, collecte de métadonnées uniquement |
| Exécution sans surveillance humaine | Planification sur une machine **disponible en continu**, reprises et alertes |
| Reproductibilité | Code, Dockerfile, Compose, DAG Airflow et configuration dans Git |
| Traçabilité | Identifiant d'exécution, provenance des articles, historique de publication |

**Hypothèse critique :** l'équipe disposera d'une machine Linux accessible et suffisamment disponible avant 7 h. Si elle est éteinte ou inaccessible, ni Docker Compose ni Airflow ne garantissent une publication ponctuelle. L'hébergement reste **à confirmer**.

## 4. Choix techniques et alternatives

### 4.1. Récupération de la presse

**Choix : flux RSS/Atom en priorité ; scraping HTML de métadonnées uniquement comme solution de secours, sous réserve d'autorisation explicite.**

| Option | Atouts | Limites / décision |
|---|---|---|
| **RSS/Atom + Python `feedparser` — retenu** | Structuré, léger, facile à automatiser ; expose souvent titre, lien, date et extrait | Flux parfois incomplets ou indisponibles ; formats et dates hétérogènes |
| **Scraping limité de métadonnées — secours conditionnel** | Peut compléter une source sans flux RSS | Fragile aux changements HTML ; contraintes juridiques/contractuelles ; **interdit si la source ne l'autorise pas** |
| **API de presse — non retenue au départ** | JSON standardisé ; recherche et filtres parfois disponibles | Quotas, couverture variable, restrictions de réutilisation et éventuels coûts |

**Décision opérationnelle :** pour une source en panne, tenter d'abord une nouvelle lecture RSS avec délai progressif. Si le flux reste indisponible, ne basculer vers l'extraction HTML **que si les conditions de la source l'autorisent et que seul un ensemble limité de métadonnées est récupéré**. Sinon, enregistrer l'échec, conserver les autres sources et signaler la couverture dégradée. Le scraping de secours **ne signifie jamais aspirer l'article intégral**.

### 4.2. Automatisation quotidienne

**Choix : Apache Airflow 3 + Docker Compose, avec LocalExecutor pour le prototype.**

| Option | Atouts | Limites / décision |
|---|---|---|
| **Apache Airflow — retenu** | DAG, historique, interface, logs et retries par tâche | Plusieurs services et ressources mémoire à prévoir |
| **systemd timers — écarté** | Léger, supervision Linux intégrée | Dépendances et reprises par tâche à développer |
| **Cron — écarté** | Simple et répandu | Historique et suivi des échecs à construire |
| **GitHub Actions planifié — écarté** | Exécution distante et logs intégrés | Horaire de démarrage non garanti |

**Fonctionnement actuel :** `gazette_daily` lance la collecte à 6 h Europe/Paris,
avec trois retries immédiats puis huit retries espacés de 30 minutes par tâche,
un seul run actif et sans rattrapage automatique.
Airflow pilote les tâches ; Compose déploie les services. PostgreSQL conserve pour
l'instant les métadonnées Airflow et les articles sont archivés en JSON.
L'exécuteur local évite Redis et les workers Celery pour ce premier palier.
La publication unique à 7 h, le stockage métier et le contrôle indépendant sont
encore à développer. Airflow ne garantit pas à lui seul le respect de cette échéance.

### 4.3. Stockage et archivage

**Choix : PostgreSQL + archivage des données brutes autorisées.**

| Option | Atouts | Limites / décision |
|---|---|---|
| **PostgreSQL + fichiers d'archive — retenu** | Transactions, contraintes d'unicité, requêtes SQL, suivi des exécutions et évolutivité | Administration, volumes persistants, sauvegardes et restauration nécessaires |
| **SQLite + JSON — écarté** | Léger, facile à mettre en route | Moins pratique pour des accès concurrents ou une extension multi-services |
| **CSV / JSON seuls — écartés** | Simples et portables | Intégrité, recherche, mises à jour et suppression de doublons plus difficiles |
| **MongoDB — écarté** | Souple pour des documents variables | Ajoute un service sans bénéfice majeur pour nos données relationnelles |

**Organisation proposée :**

- PostgreSQL : tables `sources`, `articles`, `themes`, `article_themes`, `runs`, `editions` ; liens explicites entre articles, sources et exécutions.
- Archives : fichiers JSON/XML des **seules métadonnées autorisées**, datés, avec information sur la source, hors des répertoires publics.
- Contraintes SQL : unicité sur l'identifiant ou l'URL canonique par source et sur la date d'édition.
- Volumes Docker persistants et procédure documentée de sauvegarde/restauration ; **ne pas versionner les données de production ni les secrets dans Git**.

### 4.4. Regroupement des textes en thèmes

**Statut : choix final non communiqué par l'équipe.** Pour disposer d'un cadrage exploitable, nous proposons **provisoirement TF-IDF + K-Means**, à valider au TD correspondant.

| Option | Atouts | Limites / décision |
|---|---|---|
| **TF-IDF + K-Means — proposition provisoire** | Gratuit, reproductible, explicable, facile à évaluer | Nombre de groupes à choisir ; sémantique limitée sur des textes courts |
| **Règles et mots-clés — alternative** | Très simple, entièrement explicable | Maintenance manuelle, synonymes et ambiguïtés mal gérés |
| **Embeddings + clustering — alternative** | Saisit mieux les proximités de sens | Plus de calcul, dépendance à un modèle, évaluation nécessaire |
| **LLM — non retenu initialement** | Nomme et résume facilement des sujets | Coûts ou ressources, non-déterminisme, risque d'hallucination |

**Principe :** travailler uniquement à partir des titres et extraits autorisés ; évaluer les groupes sur un échantillon annoté ; conserver la version du modèle, les paramètres et l'identifiant d'exécution. Les synthèses doivent rester factuelles et sourcées.

### 4.5. Supervision et contrôle de publication

**Choix : logs par tâche Airflow + événements Python structurés ; contrôle de publication à développer.**

| Option | Atouts | Limites / décision |
|---|---|---|
| **Logs JSON structurés + vérification — retenu** | Peu coûteux, facile à intégrer, recherche par exécution et statut | Tableaux de bord et alertes à développer/configurer |
| **Prometheus + Grafana + Alertmanager — écarté initialement** | Métriques, graphes, alertes puissantes | Plusieurs services et maintenance supplémentaires |
| **Uptime Kuma — écarté initialement** | Suivi simple de disponibilité et notifications | Une page disponible ne signifie pas qu'une édition correcte a été publiée |
| **Sentry — écarté initialement** | Analyse et regroupement des exceptions | Ne couvre pas seul les critères métier de fraîcheur et de publication |

**Événements à journaliser :** début et fin du run, durée, statut, nombre d'articles collectés/validés/rejetés, source défaillante, taux de doublons, date des articles, génération et publication, exceptions et tentatives de reprise. Chaque événement comporte un `run_id` et un horodatage.

**Contrôle indépendant :** vérifier l'existence et la validité de **l'édition du jour**, son heure de publication, la fraîcheur des articles, et l'absence de publication en double. Si le contrôle échoue, produire un statut d'échec et **déclencher une alerte** via un canal à définir (ex. mail ou webhook autorisé). Un log local seul ne suffit pas à prévenir l'équipe si la machine est indisponible : la solution d'alerte externe reste à confirmer.

### 4.6. Infrastructure décrite en code

**Choix : Docker Compose + fichiers de configuration versionnés dans Git.**

| Option | Atouts | Limites / décision |
|---|---|---|
| **Docker Compose + Git — retenu** | Configuration lisible, versionnée et facile à reproduire sur un hôte | Ne crée pas la machine hôte et ne garantit pas sa disponibilité |
| **Terraform / OpenTofu — écarté initialement** | Provisionnement déclaratif, utile pour le cloud | Complexité disproportionnée tant qu'aucune ressource cloud n'est à créer |
| **Ansible — complément possible** | Automatisation de la configuration de l'hôte | Ajoute un outil et nécessite des accès d'administration |
| **Kubernetes — écarté** | Orchestration et montée en charge avancées | Trop lourd pour un service quotidien sur machine unique |

**Fichiers :** `docker-compose.yml`, `Dockerfile`, `.env.example` (sans secret), scripts de démarrage et DAG Airflow versionnés, `README.md`, fichiers `docs/*.md`. Le stockage métier et ses migrations SQL restent à développer. Les secrets locaux sont générés dans `.env`, hors Git.

## 5. Chaîne de traitement cible

```text
DAG Airflow (collecte à 6 h Europe/Paris)
  → Conteneur de collecte (RSS ; repli conditionnel autorisé)
  → Archive brute autorisée + PostgreSQL
  → Normalisation, contrôle de qualité et déduplication
  → Regroupement par thèmes (méthode à valider)
  → Génération de la gazette et liens vers les sources
  → Publication unique à 7 h et archivage
  → Vérification indépendante + alerte si anomalie

Logs structurés et historique d'exécution à chaque étape
Infrastructure et configuration versionnées dans Git
```

## 6. Risques et parades

| Risque | Effet possible | Parade proposée |
|---|---|---|
| Flux RSS indisponible ou modifié | Articles manquants | Retries bornés, journalisation par source, autres flux ; secours HTML **uniquement si autorisé** |
| Conditions de réutilisation non respectées | Problème juridique ou blocage | Vérification des éditeurs, mention des conditions dans `sources.csv`, aucun texte intégral |
| Dates manquantes ou fuseaux incohérents | Articles trop anciens | Normalisation UTC en base, conversion `Europe/Paris` pour la publication ; rejet/quarantaine des dates invérifiables |
| Machine arrêtée / scheduler indisponible | Gazette absente à 7 h | Hébergement disponible en continu, vérification externe, reprise documentée |
| Pipeline trop long | Publication tardive | Mesurer les durées, déclencher avant 7 h, seuil d'alerte |
| Doublons / répétition après relance | Edition ou article dupliqué | Contraintes SQL, transactions, traitements idempotents |
| PostgreSQL indisponible ou volume perdu | Perte ou blocage des données | Volumes persistants, sauvegardes testées, procédure de restauration |
| Regroupements incohérents | Gazette peu lisible | Échantillon d'évaluation, paramètres/version conservés, revue des thèmes |
| Logs disponibles seulement sur l'hôte | Panne non détectée | Sonde externe de publication et canal d'alerte indépendant, à valider |
| Fuite de secrets dans Git | Compromission des services | `.gitignore`, `.env.example`, injection sécurisée des secrets |

## 7. Répartition des rôles dans l'équipe

**Noms et binômes à compléter lors de la répartition.** Chaque sujet a un pilote, un binôme de relecture/test et un livrable documenté.

| Sujet | Responsable(s) | Livrable attendu |
|---|---|---|
| 1. Collecte presse | À attribuer | `sources.csv`, collecteur RSS et politique de secours |
| 2. Planification | À attribuer | DAG Airflow, retries, historique et procédure de reprise |
| 3. Stockage | À attribuer | Schéma PostgreSQL, archivage, sauvegardes |
| 4. Regroupement | À attribuer | Comparatif des méthodes, prototype, évaluation |
| 5. Supervision | À attribuer | Schéma de logs, contrôle de publication et alertes |
| 6. Infrastructure en code | À attribuer | Docker Compose, configuration Git, déploiement reproductible |

**Responsabilité collective :** intégration de bout en bout, validation des contraintes, revue des modifications et tenue du journal d'incidents.

## 8. Documentation et suivi

| Fichier | Rôle |
|---|---|
| `docs/cadrage.md` | Besoin, périmètre, choix et risques (ce document) |
| `docs/ci-cd.md` | Stratégie de tests, intégration, déploiement et versions |
| `docs/donnees.md` | Contrats de données, schémas et dictionnaire |
| `docs/qualite.md` | Règles de validation et justification |
| `docs/mlops.md` | Modèles, expériences, paramètres et évaluation |
| `docs/exploitation.md` | Runbook, alertes, relance et restauration |
| `docs/journal.md` | Dates des incidents, diagnostics, correctifs et vérifications |

## 9. Décisions à confirmer

1. **Méthode finale de regroupement des thèmes** : TF-IDF + K-Means proposé, non encore validé.
2. **Machine d'hébergement** disponible en continu et responsable de son exploitation.
3. **Canal d'alerte indépendant**, destinataires et mécanisme de contrôle de disponibilité.
4. **Horaire de début du traitement** permettant de garantir au mieux la publication à 7 h.
5. **Liste des éditeurs et modalités d'autorisation** pour chaque RSS ou éventuel secours HTML.
6. **Noms des membres de l'équipe** et affectation des six sujets.

---

**Position de l'équipe :** RSS d'abord, extraction HTML uniquement lorsqu'elle est autorisée, Airflow et Docker Compose pour l'exécution, PostgreSQL et archives pour la traçabilité, logs structurés et contrôle métier pour la surveillance, Git pour reproduire le déploiement. Ce prototype commence par la collecte RSS ; la chaîne métier complète sera construite progressivement.
