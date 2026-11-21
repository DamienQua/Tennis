# Tennis

Pipeline Python d'analyse des matchs, de sélection Alpha 5+, de suivi des résultats
et de simulation historique. Les exports Excel et l'historique SQLite restent séparés
du code.

## Installation et exécution

Python 3.13 est utilisé par les workflows. Depuis la racine du dépôt, sous PowerShell :

```powershell
python -m venv .venv
.venv/Scripts/python.exe -m pip install -r requirements.txt
.venv/Scripts/python.exe -m pytest -q
```

[requirements.txt](requirements.txt) verrouille les dépendances directes et transitives ;
[requirements.in](requirements.in) décrit les dépendances directes. Lors d'une mise à jour,
résoudre dans un environnement neuf, reporter les versions installées, puis valider les
tests Windows et Linux avant de remplacer le verrouillage.

Configurer les variables indiquées dans [.env.example](.env.example), puis lancer :

```powershell
.venv/Scripts/python.exe main.py --no-email
.venv/Scripts/python.exe main.py --update-results
```

Sans `--no-email`, l'analyse envoie le récapitulatif SMTP. Un échec d'envoi rend la
commande en échec, après sauvegarde des résultats. Les commandes réelles nécessitent
les accès aux fournisseurs ; les tests n'utilisent ni identifiants ni archives privées.

## Fiabilité des données

- Les ELO sont chargés avant la prédiction ; les colonnes dur, terre et gazon sont
  sélectionnées explicitement dans un index réutilisé.
- Les noms complets, accents et alias connus servent à identifier les joueurs.
  Une correspondance ambiguë ne déclenche ni pari ni règlement automatique.
- Les cotes doivent provenir d'un marché vainqueur identifié, avec deux issues cohérentes
  et un statut pré-match explicite. Les formats inconnus, matchs en direct, événements
  terminés et marchés suspendus sont refusés. Les formats couverts sont illustrés dans
  [les tests fournisseurs](tests/test_odds_safety.py).
- Une collecte absente ne devient pas une statistique à zéro. Les valeurs manquantes,
  infinies ou hors limites empêchent la prédiction ou la sélection.
- Une analyse est `incomplete`, `retry` ou `complete`. Seul le dernier état empêche
  un nouveau traitement ; les échecs temporaires restent réessayables.
- La CLV requiert une observation horodatée antérieure au début, pour la même date de
  rencontre que le pari initial. Sans cette preuve, elle reste indisponible et n'entre
  pas dans la moyenne. Un report ou une revanche ne remplace pas automatiquement cette date.

Le schéma SQLite évolue à l'ouverture, sans supprimer les matchs ou paris existants.
Les anciennes CLV sans horodatage sont conservées en base mais ne sont plus présentées
comme des observations vérifiées. Le dump SQL est remplacé atomiquement.

## Modèle et calibration

[Le modèle commun](analysis/probability_model.py) calcule une probabilité logistique à
partir des différences de classement, de forme sur douze mois, de résultats en carrière
sur la surface et d'ELO. Production, calibration et backtests utilisent la même fonction
et les mêmes transformations. Les cotes théoriques sont `1 / probabilité`, sans marge.

La configuration livrée est une **référence heuristique non calibrée**. Les anciens poids
du système à points sont incompatibles et ne sont pas réutilisés comme coefficients
logistiques. Pour recalibrer à partir des archives locales :

```powershell
.venv/Scripts/python.exe -m backtest.calibrate_weights
```

Cette commande remplace [la configuration](config/calibrated_weights.json). Elle réserve
la saison la plus récente pour la validation, ou les dernières dates si une seule saison
est disponible. Aucune journée n'est partagée entre apprentissage et validation. Chaque
surface exige au moins 20 exemples d'apprentissage et 10 de validation. Un candidat n'est
retenu que si son score Brier s'améliore et si sa log-loss ne se dégrade pas sur la période
réservée ; sinon la référence est conservée. Les coefficients exacts, dates et métriques
sont enregistrés. Cela ne constitue pas une validation indépendante de rentabilité.

Les sources live et les archives n'ont pas nécessairement la même couverture de matchs
ni la même méthode de calcul ELO. L'identité de la formule ne garantit donc pas l'identité
des distributions d'entrée ; la qualité prédictive doit être suivie sur les prédictions
réellement produites.

## Simulations historiques

Placer les archives `atp_YYYY.xlsx` et `wta_YYYY.xlsx` dans `backtest/data`, puis :

```powershell
.venv/Scripts/python.exe -m backtest.run_backtest --year 2023 --gender atp
.venv/Scripts/python.exe -m backtest.run_backtest --january-2023
```

Les simulations utilisent exclusivement les archives locales, sans classement ELO actuel.
Les statistiques et ELO d'une journée ne voient que les résultats des jours antérieurs.
Les rencontres historiques ambiguës sont rejetées ; les cotes d'une revanche ne sont pas
substituées à celles du match recherché. Un modèle calibré n'est applicable qu'après la
fin de sa validation. Les matchs sans caractéristiques suffisantes sont comptés séparément.

## Tests et automatisation

[La CI](.github/workflows/ci.yml) installe les versions verrouillées, vérifie les dépendances,
la syntaxe et les tests sous Windows et Linux. Les tests isolent leur répertoire de travail
dans un dossier temporaire pour protéger la base et les exports existants.

[Le workflow quotidien unique](.github/workflows/daily_tennis_pipeline.yml) conserve les
trois passages existants. Il sauvegarde l'état même lorsqu'une phase échoue et dépose une
copie récupérable dans les artifacts GitHub avant de tenter le push sur la branche déclenchante.
Les données sont persistées dans `tennis_ai.db`, `tennis_ai_dump.sql` et l'export Excel.
