---
noteId: "e7b81d20cbb811f1a85549129aad7d1c"
tags: []

---

# Stratégie CI/CD
1. GitHub Actions s'exécute sur push, pull request et déclenchement manuel.
2. Le lint Ruff doit réussir avant les tests Python 3.12.
3. Pytest vérifie fixtures RSS/Atom, dates, reprises, catalogue réel et CLI locale.
4. Les tests doivent réussir avant la construction de l'image multi-étapes.
5. Le job build démarre PostgreSQL/Airflow et vérifie l'import du DAG et l'utilisateur non root.
6. La CI ne collecte pas de presse : les tests HTTP utilisent un serveur local.
7. L'image construite est transférée au job push sans reconstruction.
8. Sur push réussi, GITHUB_TOKEN publie dans ghcr.io avec packages: write limité à ce job.
9. Deux tags identifient l'image : horodatage UTC + SHA court, et SHA complet.
10. Un test cassé bloque build/push ; preuves rouge/vert et revue croisée vont dans le journal.
