# Console de contrôle du pipeline Gazette

Double-cliquer sur **`VOIR_PIPELINE.cmd`**, à la racine du projet.
Docker Desktop et les services doivent être démarrés. Le programme indique
comment lancer `bin/dev.ps1` si la stack n'est pas disponible.

Le lanceur utilise PowerShell et le Python déjà présent dans le conteneur Airflow :
aucun Python supplémentaire n'est nécessaire sur Windows. Il copie uniquement
le programme de visite dans `/tmp` du conteneur avant de le lancer.

## Menu

- **1 ou Entrée** : lire les résultats existants, sans collecte ni notification.
- **2** : lancer un vrai DAG complet, suivre ses étapes, puis inspecter ses données.
  Les tables et fichiers sont actualisés comme dans le pipeline habituel.
  Une anomalie réelle suit le canal d'alerte configuré ; aucun message de test n'est envoyé.
- **Q** : quitter.

Appuyer sur Entrée entre les étapes ; Ctrl+C interrompt la visite.
Le choix 2 utilise `airflow dags test` pour le même DAG à cinq tâches : ce n'est
pas un nouveau planning et ce n'est pas une preuve d'un déclenchement par le scheduler.
Les vérifications du mode 1 ne modifient pas la base métier.

## Les huit écrans

1. Catalogue, URL, erreurs et sources en sommeil.
2. Nombre de bruts par source et exemple du vrai JSON.
3. Comparaison titre/résumé/date avant et après normalisation, sans écraser le brut.
4. Nombre de propres/rejets et motifs des rejets.
5. Contrôles sur PostgreSQL et lecture du dernier rapport qualité.
6. Dernier run MLOps : fenêtre, version du modèle, paramètres et métriques.
7. Liste des thèmes. Saisir un **label** pour lire tous ses titres, résumés et liens ;
  saisir **B** pour lire les articles isolés ; Entrée passe à l'étape suivante.
8. Cohérence des effectifs, SHA-256 des artefacts, dimensions et extrait d'un vecteur.

Les tables courantes peuvent évoluer pendant la visite puisque le scheduler reste
actif. Les articles d'un thème sont lus dans les instantanés de son run, pas dans
la table propre courante. L'évaluation éditoriale des thèmes est distincte des
contrôles techniques : cohérence du sujet, pertinence des affectations et qualité du nommage.

## Commandes alternatives PowerShell

```powershell
# Menu interactif
powershell.exe -NoProfile -ExecutionPolicy Bypass -File bin/voir_pipeline.ps1

# Lecture seule, avec pauses
powershell.exe -NoProfile -ExecutionPolicy Bypass -File bin/voir_pipeline.ps1 -LectureSeule

# Inspection sans pauses, utile pour conserver une sortie texte
powershell.exe -NoProfile -ExecutionPolicy Bypass -File bin/voir_pipeline.ps1 -LectureSeule -SansPause

# Vraie exécution suivie d'une inspection sans pauses
powershell.exe -NoProfile -ExecutionPolicy Bypass -File bin/voir_pipeline.ps1 -Lancer -SansPause
```

Les journaux complets des exécutions lancées par le programme sont conservés dans
`data/verification/`, hors Git. Un échec du DAG ou de la cohérence produit un code
de sortie non nul. Aucun mot de passe ni URL de webhook n'est affiché par la visite.

Fichiers : `VOIR_PIPELINE.cmd` ouvre le lanceur Windows, `bin/voir_pipeline.ps1`
prépare l'exécution Docker et `bin/voir_pipeline.py` affiche et vérifie les vraies données.
