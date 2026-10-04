# Résultats du benchmark sur 20 graines

Le système améliore ses prédictions dans ce petit laboratoire, mais sa
progression reste instable. À 200 expériences, la meilleure moyenne est
hyperbolique avec exploration aléatoire. La sélection active fait moins
bien que le hasard dans les deux géométries.

Code exécuté : 9a081d94630a7f8f052df3d36d2d1f5889a84983.
[Exécution GitHub Actions](https://github.com/Setharkk/Remake-setharkk/actions/runs/37165721581).
Le [protocole fixé avant exécution](BENCHMARK_PROTOCOL.md) donne les budgets
et les comparaisons. Le réseau et ses règles d'apprentissage sont identiques
à la version issue de la deuxième revue.

## Exécution et validation

- Graines 0 à 19 ; quatre conditions ; 200 expériences par condition.
- 80 conditions et 16 000 expériences d'entraînement par système.
- CPU, float64, PyTorch 2.14.1+cpu.
- Python 3.11.9 sous Windows et 3.11.16 sous Linux.
- 25 tests réussis sur chaque système, puis benchmark et audit réussis.
- Budgets, séparation des données, métriques finies, journaux et
  reproduction des prédictions depuis les poids sauvegardés vérifiés.
- Les 80 séquences état/action/résultat sont identiques entre Windows
  et Linux. L'écart maximal des Brier individuels est inférieur à 2.1e-15.

Les tableaux présentent les résultats Windows ; Linux reproduit ces valeurs.
Les deux systèmes constituent un contrôle de reproduction, pas 40 graines
indépendantes.

## Courbes de progression

Brier moyen sur les huit couples réservés par graine : plus faible est
meilleur. Les références sur ce contrôle sont 0.25 pour des probabilités
uniformes et 0.21875 pour l'état inchangé avec succès à 0.5.

| Condition | Initialisation | 50 expériences | 100 expériences | 200 expériences |
|---|---:|---:|---:|---:|
| Hyperbolique active | 0.250630 | 0.212556 | 0.199399 | 0.205973 |
| Hyperbolique aléatoire | 0.250630 | 0.202396 | 0.187742 | 0.193199 |
| Euclidienne active | 0.250606 | 0.213105 | 0.204389 | 0.221775 |
| Euclidienne aléatoire | 0.250606 | 0.201121 | 0.185610 | 0.205951 |

La condition hyperbolique aléatoire passe de 0.250630 à 0.193199 en moyenne,
soit environ 22.9 % de baisse depuis l'initialisation. Son Brier final est
environ 11.7 % inférieur à la référence d'état inchangé. La moyenne
euclidienne active, 0.221775, reste moins bonne que cette référence.

| Condition | Écart-type final | Meilleure que son initialisation | Meilleure que l'état inchangé | Exactitude des 4 bits | NLL moyenne |
|---|---:|---:|---:|---:|---:|
| Hyperbolique active | 0.035435 | 17/20 | 12/20 | 31.87 % | 2.601199 |
| Hyperbolique aléatoire | 0.031291 | 19/20 | 17/20 | 37.50 % | 2.502033 |
| Euclidienne active | 0.032289 | 16/20 | 8/20 | 27.50 % | 2.946764 |
| Euclidienne aléatoire | 0.027769 | 19/20 | 14/20 | 33.75 % | 2.769437 |

L'exactitude exige que les trois présences de fichiers et le succès soient
tous corrects. Même la meilleure condition moyenne n'atteint que 37.5 %.
Le NLL uniforme vaut 4 ln(2), soit environ 2.772589 ; la NLL moyenne de
l'euclidienne active est moins bonne. Brier et NLL ne mesurent pas la même
chose ; la NLL pénalise fortement les erreurs confiantes.

## Régressions malgré davantage d'expériences

| Condition | Pire à 200 qu'à 50 | Pire à 200 qu'à 100 | Brier moyen à 200 moins Brier moyen à 100 |
|---|---:|---:|---:|
| Hyperbolique active | 10/20 | 10/20 | 0.006574 |
| Hyperbolique aléatoire | 8/20 | 10/20 | 0.005457 |
| Euclidienne active | 12/20 | 13/20 | 0.017386 |
| Euclidienne aléatoire | 13/20 | 18/20 | 0.020341 |

Les quatre moyennes sont moins bonnes à 200 qu'à 100. L'euclidienne aléatoire
se dégrade dans 18 graines sur 20 sur cet intervalle. À 100 expériences,
elle est légèrement meilleure en moyenne que l'hyperbolique aléatoire :
le classement dépend donc aussi de la durée d'entraînement.

Les points à 100 ne deviennent pas automatiquement un critère d'arrêt :
choisir l'arrêt sur ces cas réservés réutiliserait le contrôle pour régler
le système. Une future décision d'arrêt demanderait un jeu de validation
distinct.

## Comparaisons appariées

Chaque différence compare les mêmes graines et les mêmes cas réservés.
Une valeur négative favorise la première condition.

| Comparaison | Différence moyenne de Brier | Intervalle bootstrap descriptif à 95 % | Première condition meilleure |
|---|---:|---:|---:|
| Hyperbolique active moins Hyperbolique aléatoire | 0.012774 | [-0.002978 ; 0.029364] | 7/20 |
| Euclidienne active moins Euclidienne aléatoire | 0.015824 | [0.001172 ; 0.030237] | 6/20 |
| Hyperbolique active moins Euclidienne active | -0.015802 | [-0.030009 ; -0.000987] | 13/20 |
| Hyperbolique aléatoire moins Euclidienne aléatoire | -0.012752 | [-0.022798 ; -0.003665] | 14/20 |

La stratégie active gagne dans seulement 7 graines sur 20 en hyperbolique
et 6 sur 20 en euclidien. L'hyperbolique aléatoire gagne contre l'euclidienne
aléatoire dans 14 graines sur 20 à 200 expériences. Ces mesures soutiennent
un avantage observé de cette condition ici ; elles ne démontrent pas une
supériorité générale de la géométrie.

Les intervalles résument la variabilité des graines dans un seul monde de
32 couples. Les couples réservés se recouvrent entre graines et ces
comparaisons ne sont pas des garanties sur d'autres environnements.

## Répartition des expériences

| Condition | Couples distincts moyens | Part du couple le plus répété | Créer | Déplacer | Renommer | Lire |
|---|---:|---:|---:|---:|---:|---:|
| Hyperbolique active | 23.65/24 | 12.30 % | 55.50 | 48.60 | 48.05 | 47.85 |
| Hyperbolique aléatoire | 24.00/24 | 7.00 % | 48.40 | 48.95 | 52.80 | 49.85 |
| Euclidienne active | 23.60/24 | 13.65 % | 54.10 | 52.05 | 52.95 | 40.90 |
| Euclidienne aléatoire | 24.00/24 | 7.00 % | 48.40 | 48.95 | 52.80 | 49.85 |

Les stratégies actives couvrent presque tous les 24 couples accessibles.
Une explication par une absence générale de couverture n'est donc pas
soutenue par ces mesures. Elles concentrent davantage les répétitions :
le couple le plus fréquent reçoit en moyenne 12.3 % ou 13.65 % des
expériences, contre 7 % dans les deux conditions aléatoires. Cette
observation indique un déséquilibre ; elle ne prouve pas qu'il cause
la différence de performance.

## Compétences mal prédites

| Condition | Créer | Déplacer | Renommer | Lire |
|---|---:|---:|---:|---:|
| Hyperbolique active | 0.208546 | 0.267661 | 0.255959 | 0.091726 |
| Hyperbolique aléatoire | 0.209023 | 0.244699 | 0.242596 | 0.076478 |
| Euclidienne active | 0.217827 | 0.306075 | 0.260644 | 0.102553 |
| Euclidienne aléatoire | 0.212520 | 0.266481 | 0.267111 | 0.077692 |
| État inchangé | 0.187500 | 0.312500 | 0.312500 | 0.062500 |

Les déplacements et renommages ont les plus grosses erreurs absolues,
mais bénéficient aussi des plus grands gains par rapport à l'état inchangé.
Pour créer et lire, les quatre conditions restent moins bonnes en moyenne
que cette référence simple.

Deux exemples issus des diagnostics :

- Hyperbolique active, graine 9 : état [1,1,0], action déplacer. La destination
  existe déjà : le résultat réel est [1,1,0,0]. Le modèle prédit environ
  [0.095,0.999,0.952,0.716], avec 71.6 % de probabilité de succès et une
  forte probabilité d'apparition du fichier renommé. Son Brier sur ce cas
  est 0.559180, contre 0.0625 pour l'état inchangé.
- Euclidienne active, graine 1 : état [0,0,0], action créer. Le résultat réel
  est [1,0,0,1]. Le modèle prédit environ [0.080,0.002,0.005,0.080] :
  il sous-estime fortement la création et sa réussite.

L'ordre de l'état est [A/item.txt, B/item.txt, A/renamed.txt] ; le résultat
ajoute le succès comme quatrième bit. Ces exemples sont des erreurs de
prédiction ; les opérations du laboratoire ont produit les résultats
effectivement observés.

## Décision pour la suite

L'apprentissage des conséquences produit un gain mesurable, mais la
sélection active actuelle ne remplit pas son objectif d'améliorer les
prédictions davantage que le hasard. Le modèle présente aussi des
régressions et des erreurs confiantes sur des opérations simples.

La priorité suivante est d'expliquer ces régressions en mesurant
séparément l'erreur sur les expériences apprises, une validation distincte
et le contrôle final, dans un ensemble de situations plus vaste. Le monde
actuel ne contient que deux situations de succès pour déplacer, et deux pour
renommer : cela limite fortement trois partitions équilibrées. Ces mesures
permettront de tester l'hypothèse de surapprentissage
et les réglages de stabilité sans régler le système sur son contrôle final.
Les mesures actuelles seules ne permettent pas d'établir la cause.

La sauvegarde complète et la reprise restent nécessaires pour le futur
fonctionnement continu ; elles ne corrigeraient pas ces défauts de
prédiction. La création d'un essaim ne découle pas de ce benchmark.

## Données conservées

- [Analyse complète Windows](benchmark_results/run_37165721581/analysis_windows.json)
- [Résumé Linux](benchmark_results/run_37165721581/analysis_linux_summary.json)
- [Brier et diagnostics des 80 conditions](benchmark_results/run_37165721581/runs_windows.csv)
- [Artefact Windows : traces, poids, configurations et métriques](https://github.com/Setharkk/Remake-setharkk/actions/runs/37165721581/artifacts/11289004390)
- [Artefact Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37165721581/artifacts/11288639246)

Les données JSON et CSV du dépôt restent versionnées. Les artefacts
GitHub Actions sont soumis à la durée de conservation configurée.

Pour reproduire depuis la racine du dépôt, après installation :

~~~powershell
.\cortex_lab_v0\.venv\Scripts\python.exe -m cortex_lab_v0.run --steps 200 --seeds 0 1 2 3 4 5 6 7 8 9 10 11 12 13 14 15 16 17 18 19 --evaluate-every 50
.\cortex_lab_v0\.venv\Scripts\python.exe -m cortex_lab_v0.analyze "cortex_lab_v0/cortex_runs/<identifiant>"
~~~

La configuration de chaque run enregistre la version logicielle. Les
mesures ci-dessus utilisent PyTorch 2.14.1+cpu.
