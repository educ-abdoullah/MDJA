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
dans `sources.csv` en UTF-8 ; renseigner le flux réel et vérifier les conditions avant
activation. Conserver une seule source active pour la démonstration initiale.

Consigner les incidents et correctifs dans `docs/journal.md`. Toute modification du
contrat CSV doit être accompagnée d'un test utilisant le catalogue du dépôt.

## Montrer qu'un test cassé bloque la CI

Sur une branche de démonstration, remplacer `Article récent` par `Article cassé` dans
`tests/fixtures/sample_rss.xml`, lancer les tests puis pousser cette branche.
Le test du titre doit échouer ; les jobs build et push doivent être ignorés.
Restaurer ensuite la fixture et pousser un nouveau commit : la CI doit redevenir verte.
Conserver les deux liens d'exécution dans le journal. Ne pas fusionner la version cassée.

## Revue croisée

Une autre équipe clone le dépôt et suit les deux commandes du README sur sa machine.
Elle remplit `docs/revue-croisee.md` : système, commit, commandes, fichier JSON obtenu,
résultat des tests et premier bug rencontré. Nous faisons la même vérification sur
son dépôt. Cette validation humaine complète les tests automatiques.
