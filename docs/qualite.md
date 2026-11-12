# Qualité des articles — TD4

Mise à jour du 12 novembre 2026. Les modules sont implémentés dans
`src/gazette/processing/` et exécutés après la collecte par `gazette_daily`,
toutes les 30 minutes : normalisation, règles, stockage, rapport et contrôles.

## Normalisation et règles

Les fonctions pures retirent HTML et scripts, décodent les entités, uniformisent
les espaces, réparent les encodages réversibles, convertissent les dates en UTC
et bornent le résumé à 500 caractères. Les JSON bruts sont conservés intacts.

| ID | Ce qui est rejeté | Exemple / justification |
|---|---|---|
| R01_publi | Mention explicite de publicité ou partenariat dans titre/rubrique | « Contenu partenaire » ; éviter le promotionnel |
| R02_horoscope | Horoscope explicite | « Horoscope du jour » ; hors périmètre |
| R03_programme_tv | Programme/grille TV explicite | « Programme TV » ; hors périmètre |
| R04_jeux_concours | Quiz, sudoku, mots croisés, concours explicites | Quiz Ouest-France observé |
| R05_titre_vide | Titre vide après nettoyage | Espaces ou balises seuls |
| R06_date_future | Publication dépassant maintenant de plus de 5 min | Tolérance partagée avec le contrôle SQL |
| R07_encodage | Corruption persistante après réparation prudente | Caractère de remplacement ou mojibake |
| R08_doublon_exact | Même source, titre et résumé normalisés identiques | Conserver la première version |
| R09_titre_generique | Titre égal à « Début de direct » | Exemple L’Humanité observé |
| R10_doublon_approximatif | Même source, titres >= 6 mots distincts et Jaccard >= 0,85 ; résumés non vides et Jaccard >= 0,90 | Écarter les quasi-copies sans supprimer les angles différents |

Jaccard = mots communs / ensemble des mots des deux textes. Les mots sont
comparés sans distinction de casse. Seuls les articles déjà retenus sont comparés.
Les copies entre médias restent conservées pour préserver la diversité éditoriale :
c'est une restriction de périmètre à expliquer au rendu. Les seuils de R10 sont
conservateurs et ne détectent pas tous les doublons possibles.

## Observations réelles et limites

L'export initial contenait 299 articles de six sources. Deux pollueurs nets ont
été identifiés : le quiz Ouest-France (ID brut
`621b6201873ce733a4d9fcd99d74648404195c5c236bc80426d9b9fa4bc448f9`)
et « Début de direct » de L’Humanité (ID brut
`36f8b82ad5b18929d210146b071743879ad4b9aecf738e05f95c79768406ebe0`).
Le rapport enregistré à 10:16 UTC indique 354 bruts, 352 propres et 2 rejets.
Ce résultat précède R10 ; ne pas le présenter comme le bilan des nouvelles règles.
Les dix pollueurs réels demandés ne sont pas encore documentés ; ne pas en inventer.

## Contrôles, rapports et alertes

Après chaque traitement, les requêtes SQL vérifient titres, dates (tolérance 5 min),
unicité exacte, références brutes, absence de décisions contradictoires et couverture.
Un taux de rejet supérieur à 80 % déclenche une alerte ; une source sans article
est non applicable pour ce taux, pas implicitement saine.
Les chiffres sont émis en JSON dans les logs Airflow. Le webhook Discord est fourni
par `.env` et ne doit pas apparaître dans Git ou les preuves de validation.

Le traitement réexamine tous les bruts : les nombres du rapport portent sur ce lot
complet, pas seulement les nouveaux articles du cycle. Le DAG ajoute son run_id.
Les rapports sont archivés dans `rapports/` avec date et horodatage.
La référence brute permet de retrouver le fichier et sa source depuis un propre/rejet.

## Journal des ajustements

- 12 novembre : ajout de R10 pour couvrir le dédoublonnage approximatif du TD4.
- 12 novembre : tolérance de cinq minutes commune au filtrage et au contrôle SQL,
  pour éviter qu'un article accepté déclenche immédiatement une alerte de date.
- À poursuivre : lire les rapports trois matins consécutifs et consigner les effets
  observés ainsi que les seuils ajustés. Cette observation n'est pas encore réalisée.

Voir [donnees.md](donnees.md) pour le contrat et la rétention,
et [validation-td4.md](validation-td4.md) pour les preuves et limites de validation.
