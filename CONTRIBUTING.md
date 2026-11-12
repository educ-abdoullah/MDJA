---
noteId: "8f1b12e0cba311f1a85549129aad7d1c"
tags: []
---

# Contribuer

1. Cloner le dépôt, créer une branche et lancer `sh bin/dev` (Windows : `bin/dev.ps1`).
2. Modifier le collecteur dans `src/gazette/`, les DAG dans `dags/` et l'infrastructure dans `infra/`.
3. Ajouter une fixture enregistrée et un test pour toute nouvelle règle de parsing.
4. Lancer `sh bin/test` (Windows : `bin/test.ps1`) et vérifier les changements dans Docker.
5. Ouvrir une pull request décrivant le changement et ses validations ; attendre la CI verte.

Ne pas committer `.env`, données, logs, caches ou mots de passe. Ajouter les sources
dans `sources.csv` en UTF-8 avec le format à points-virgules documenté dans
`docs/donnees.md`. Les huit sources sont importées ; leur état opérationnel est
conservé dans PostgreSQL et ne doit pas être réinitialisé à chaque import.

Consigner les incidents et correctifs dans `docs/Archive/journal.md`. Toute modification du
contrat CSV doit être accompagnée d'un test utilisant le catalogue du dépôt.

## Montrer qu'un test cassé bloque la CI

Sur une branche de démonstration, remplacer `Article récent` par `Article cassé` dans
`tests/fixtures/sample_rss.xml`, lancer les tests puis pousser cette branche.
Le test du titre doit échouer ; les jobs build et push doivent être ignorés.
Restaurer ensuite la fixture et pousser un nouveau commit : la CI doit redevenir verte.
Conserver les deux liens d'exécution dans le journal. Ne pas fusionner la version cassée.

## Revue croisée

Une autre équipe clone le dépôt et suit les deux commandes du README sur sa machine.
Elle remplit `docs/Archive/revue-croisee.md` : système, commit, commandes, fichier JSON obtenu,
résultat des tests et premier bug rencontré. Nous faisons la même vérification sur
son dépôt. Cette validation humaine complète les tests automatiques.


## TD5

Installer aussi les dépendances ML via `requirements-dev.txt` (qui inclut la chaîne
requirements.txt → requirements-ml.txt), ou utiliser les images Docker.
Modifier les paramètres dans `config/clustering.yaml` et conserver le modèle à une
révision de commit immuable. Ne pas changer une migration déjà appliquée.
Les tests de cache et de suivi utilisent un encodeur contrôlé et PostgreSQL en schémas
isolés. Le modèle réel est testé séparément par `bin/verify_mlops.py` sur dix articles
propres récents ; conserver son journal comme preuve sans imposer de réseau à la CI.
Ne pas committer le modèle, les données, les vecteurs ou les secrets.
Documenter dans `docs/mlops.md` chaque observation éditoriale et comparer des runs
sur les mêmes instantanés avant d'attribuer un effet aux paramètres.
