# Validation TD4 — 12 novembre 2026

## Corrections réalisées

- Ruff : imports, éléments inutilisés et mise en forme corrigés sans désactiver les règles.
- CI : contrôle des quatre tâches, de leur ordre, du calendrier toutes les 30 minutes,
  de `catchup=False`, d'un seul run actif, de zéro retry Airflow et de la sérialisation.
- Dates : tolérance commune de cinq minutes, utilisée en Python et dans la requête SQL paramétrée.
- R10 : dédoublonnage approximatif intra-source par Jaccard titre/résumé,
  avec tests de quasi-copies, d'angles différents et de sources différentes.
- Rapport : identifiant Airflow ajouté ; périmètre précisé comme recalcul de tous les bruts.
- Bootstrap : préparation du dossier de rapports et de ses droits.
- Documentation : README, règles et contrat actualisés ; rétention définie, sans purge activée.

## Preuves obtenues

- Ruff : tous les contrôles réussissent.
- Suite locale : 75 tests réussis, 6 tests PostgreSQL ignorés sans connexion.
- Suite Docker avec PostgreSQL : **81 tests réussis, aucun ignoré**, y compris un
  nouveau test réel de recalcul qualité, rejouabilité et contrôle SQL en schéma isolé.
- Migrations 001 et 002 présentes dans la base locale.
- Assertions de la CI et sérialisation vérifiées dans Airflow 3.3.2.
- Run manuel `manual__2026-11-12T12:37:52.650994+00:00` : quatre tâches réussies,
  fin à 13:38:05 heure de Paris ; 131 bruts classés, 131 propres, aucun rejet ni anomalie.
  Journal local hors Git : `.validation/td4-run.log`.
- Run planifié `scheduled__2026-11-12T12:30:00+00:00` : quatre tâches réussies,
  exécuté au redémarrage entre 13:38:25 et 13:38:37 heure de Paris.
  État final vérifié : **132 bruts, 132 propres, zéro rejet**. Un article supplémentaire
  entre les deux collectes explique la différence de taille.
- Rapports horodatés `rapports/qualite-2026-11-12T12-38-05-233465Z.md` et
  `rapports/qualite-2026-11-12T12-38-35-918311Z.md` ; rapport quotidien actualisé.
- Alerte : un unique message de test envoyé après autorisation explicite de l'utilisateur ;
  Discord a accepté la requête (`gazette_quality_test_alert_sent`). La réception visuelle
  dans le canal reste à confirmer par l'équipe. Aucune URL secrète n'est reproduite ici.
- PostgreSQL, API Airflow, scheduler et processeur de DAG sains ; DAG actif.

Les nombres du rapport historique à 354 articles sont issus d'un autre état de données.
La base démarrée pour cette validation contenait initialement six bruts et aucune décision.
Aucune réinitialisation ni suppression des données métier n'a été effectuée pendant la validation.

## Limites restantes

- Trois flux en erreur sur le run manuel : La Provence HTTP 404, Sud Ouest et
  Le Télégramme HTTP 403. Un run vert ne signifie pas huit sources réussies.
  Le collecteur isole et compte ces erreurs ; après trois cycles échoués, sommeil.
- Dix pollueurs réels : seuls deux exemples historiques sont documentés.
- R10 conserve les quasi-copies entre médias : périmètre intra-source à expliquer
  à l'enseignant ; cette adaptation ne prétend pas supprimer toutes les dépêches reprises.
- Un run manuel et un run planifié sont prouvés, pas deux périodes planifiées successives.
  Le suivi de trois matinées reste à réaliser, avec ajustements justifiés des règles.
- Le webhook a été testé par message simulé ; la livraison d'une anomalie réelle
  provoquée en base n'a pas été testée en altérant les données métier.
- La CI distante n'a pas été lancée ni le code poussé : ces actions restent manuelles.
- La rétention est écrite ; aucune purge automatique ni archive froide n'est installée.

## Avant le TD5

La table propre et le pipeline constituent un socle testé pour les embeddings.
Il faudra sélectionner explicitement les publications des dernières 24 heures et
faire évoluer le recalcul complet (`DELETE` puis insertion) avant de créer des
références persistantes depuis les thèmes, pour ne pas casser les clés étrangères.
Le TD5 n'a pas été commencé lors de cette finalisation.
