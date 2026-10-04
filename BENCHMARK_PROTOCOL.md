# Benchmark de progression : 20 graines

Version du réseau et des règles d'apprentissage :
03df3a58f5553bf8924dafe05fba997e253cf5e3.
Le script d'analyse et la configuration CI sont ajoutés pour ce benchmark ;
core.py et run.py restent identiques.

## Protocole fixé avant exécution

- CPU, double précision ; même protocole version 2.
- Graines 0 à 19, toutes conservées dans l'analyse.
- Quatre conditions : hyperbolique/euclidienne et active/aléatoire.
- 200 expériences par condition, soit 80 conditions et 16 000 expériences
  d'entraînement par système d'exploitation.
- Trois membres de 72 paramètres. Trois mises à jour par membre et expérience,
  lots de 32 : 1800 mises à jour d'optimiseur par condition.
- 24 couples d'entraînement et 8 couples réservés par graine.
- Mêmes couples réservés et mêmes huit expériences initiales pour les quatre
  conditions d'une graine. Les deux variantes aléatoires reçoivent toute la
  même séquence d'expériences.
- Évaluations à 0, 50, 100, 150 et 200 expériences. Les points demandés
  pour le rapport sont 0, 50, 100 et 200.
- Aucun changement de paramètres ou de sélection pendant l'expérience à
  partir des scores réservés. Aucun arrêt anticipé ni retrait de graine.

## Mesures et contrôles

Mesure principale : Brier sur les huit couples réservés, plus faible est
meilleur. Comparer la moyenne, l'écart-type et chaque graine à l'initialisation,
aux probabilités uniformes et à la prédiction d'état inchangé.

Les comparaisons finales sont appariées par graine : actif moins aléatoire
dans chaque géométrie, et hyperbolique moins euclidien pour chaque stratégie.
Une différence négative favorise la première condition. Les intervalles
bootstrap sont descriptifs, calculés sur les graines avec 10 000 tirages et
la graine d'analyse 39017 ; ce ne sont pas des garanties sur d'autres mondes.

Le diagnostic comprend les régressions de 50 ou 100 à 200 expériences,
la couverture des couples, leur répétition, la répartition par action,
les erreurs par action et les trois cas réservés les plus mal prédits par
condition et graine. Les poids sont rechargés pour vérifier que leurs
prédictions reproduisent le Brier final.

L'analyse rejette les conditions manquantes, budgets incohérents,
métriques non finies, incohérences entre CSV et résumé, ou utilisation
de couples réservés à l'entraînement.

## Portée

Les graines font varier l'initialisation, les choix d'expériences et la
séparation des données dans le même monde de 32 couples. Les cas réservés
se recouvrent entre graines. Ce benchmark mesure cette variabilité ; il ne
mesure pas la généralisation à de nouveaux environnements ou l'autonomie
du bureau. Les résultats Windows et Linux valident la reproduction sur
deux runners CPU, pas deux expériences statistiques indépendantes.

Les résultats seront conservés dans les artefacts CI et un rapport versionné.
Les courbes consolidées sont dans benchmark-rows.csv ; les diagnostics dans
analysis.json. Une performance faible sera rapportée sans modifier les
réglages après coup.
