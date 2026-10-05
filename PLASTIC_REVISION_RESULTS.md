# Révision plastique : délais et montée à l'échelle

Ce rapport conserve les mesures du format 7. Le format 8 et les nouvelles
validations sont décrits dans [PRIORITY_FIXES.md](PRIORITY_FIXES.md).

Le moteur de format 7 conserve le réseau sur S² et passe 139 tests sous
Windows et Linux. Le pire délai de compétence complète après bruit initial
passe de 21 000 à 10 000 retours globaux sur les trois graines initiales.
Les essais sur 64 symboles et 16 contextes passent aussi leurs critères.
Ces résultats décrivent un apprentissage synthétique limité.

L'initialisation depuis les poids plastiques est effective, mais son
avantage propre sur le délai n'est pas établi : l'ablation sans transfert
obtient les mêmes délais sur les trois graines. Le changement de validation
produit le gain mesuré. Un raffinement prospectif du programme déjà admis
permet en plus de servir de meilleurs poids lorsque les bonnes actions
étaient conservées avec des probabilités trop prudentes.

## Sources et reproduction

Moteur testé : `b5c86166fb22f69c1e441acce5d47ec5915a55c8`.
Identité `first_piece.plastic-revision-s2.v2`, checkpoint 7.
Les [instructions](PLASTIC_REVISION.md) donnent les imports et le contrat.
Le [protocole](PLASTIC_REVISION_PROTOCOL.md) conserve les budgets, formules,
critères et corrections apportées après les itérations échouées.

- [139 tests et cinq cas de délai sur les deux systèmes](https://github.com/Setharkk/Remake-setharkk/actions/runs/37242119764).
- [30 cas indépendants réussis](https://github.com/Setharkk/Remake-setharkk/actions/runs/37242119826).
- [Tests et validations des corrections](https://github.com/Setharkk/Remake-setharkk/actions/runs/37242119811).
- Données complètes : [Linux](plastic_revision_results/linux/index.json), [Windows](plastic_revision_results/windows/index.json).
- [Comparaison numérique](plastic_revision_results/comparison.json) et [itérations échouées](plastic_revision_results/failed_iterations).

Les deux systèmes exécutent 17 cas de comparaison/ablation et trois cas
de montée à l'échelle chacun : 5 336 000 retours d'apprentissage principaux
par système, plus les copies de reprise. Les fonctions de mesure restent
les mêmes pour les exécutions séquentielles et indépendantes. Chaque cas
repart d'un modèle neuf.

La référence du benchmark est le mode calibré de format 5. Elle utilise
le même correctif numérique partagé du logarithme sphérique ; son algorithme
de validation et sa calibration restent ceux de la référence historique.

## Délai avant compétence complète

Les actions d'entraînement sont uniformes, identiques entre modes.
Après 40 000 retours de bruit indépendant, le signal reçoit 40 000 retours,
soit 10 000 par contexte. Les sondes sont espacées de 1 000 retours globaux,
avec 512 épisodes par contexte. Le premier point où les quatre contextes
dépassent 95 % doit être confirmé à la sonde suivante.

| Graine | Mode calibré | Révision | Confirmation de la révision |
|---|---:|---:|---:|
| 0 | 21 000 | 10 000 | 11 000 |
| 1 | 5 000 | 1 000 | 2 000 |
| 2 | 9 000 | 2 000 | 3 000 |
| 17 | 21 000 | 1 000 | 2 000 |
| 23 | 6 000 | 1 000 | 2 000 |

Les graines 0/1/2 sont les graines de développement. Les graines 17 et 23
ont été ajoutées avant leur exécution, après les corrections.
Cet échantillon reste petit et les mondes partagent la même famille de règles.

La première admission de la révision arrive à 960, 960 et 1 472 retours
de signal sur les graines 0/1/2. Elle ne prouve pas une compétence complète :
sur la graine 0, la politique initialement admise réussit autour de 87,5 %.
La mesure de délai complète distingue donc une admission partielle du résultat
de toutes les sondes.

## Ablations et conservation

| Graine | Révision complète | Initialisation neutre, nouvelle validation | Poids plastiques, ancienne validation |
|---|---:|---:|---:|
| 0 | 10 000 | 10 000 | 21 000 |
| 1 | 1 000 | 1 000 | 5 000 |
| 2 | 2 000 | 2 000 | 9 000 |

Le facteur « nouvelle validation » regroupe référence figée, contrôle des
taux de base par contexte, regards, bornes et réexamens. Le mode révisé
dispose aussi du raffinement de confiance. Cette expérience ne permet pas
d'attribuer le gain à chaque mécanisme isolément. Elle ne démontre pas
un avantage autonome du transfert de poids.

Les trois cas de rétention conservent la compétence et ne produisent aucune
admission pendant les 80 000 retours de bruit uniforme. Brier observé :
0,189144 / 0,189295 / 0,187320 ; perte logarithmique tronquée :
0,567709 / 0,567718 / 0,563628. Les seuils étaient 0,205 et 0,62.
À 500 retours de récupération par contexte, le pire Brier structuré vaut
7,49e-5, sous le seuil 0,025.

Les cas de taux variables 0,1/0,6 conservent aussi la compétence sans
admission sous bruit. Le contrôle conditionnel évite de traiter le seul
taux de résultat d'un contexte comme une compétence d'action.
Les six changements successifs du contexte 0 se terminent à 100 % dans
les quatre contextes. Les admissions de remplacement prennent 711 à
2 081 retours du contexte ciblé selon la phase et la graine.

Le succès de politique sous bruit désigne le classement correct pour
l'ancienne règle lors des sondes structurées. Les résultats réellement
observés sous bruit restent proches de 25 % pour le bruit uniforme.
Les probabilités s'aplatissent pendant cette phase ; leur Brier sur une
sonde structurée est alors élevé. Cela ne signifie pas que la règle a
été effacée.

## 64 symboles et 16 contextes

Par graine : 16 000 retours indépendants, 160 000 structurés,
64 000 indépendants, 32 000 de récupération, puis 160 000 avec changement
du seul contexte 0. Les phases structurées principale et finale donnent
10 000 retours à chaque contexte. Les sondes ont 128 épisodes par contexte.
Le contexte neuf 16 reçoit une sonde de 512 épisodes et aucun label appris.

| Graine | Brier du bruit | Perte tronquée du bruit | Pire Brier à 512 retours de récupération/contexte | Succès final et contexte neuf | Pic JSON échantillonné, octets |
|---|---:|---:|---:|---:|---:|
| 0 | 0.192210 | 0.579204 | 2.700e-6 | 100 % | 1 720 858 |
| 1 | 0.192758 | 0.580553 | 2.710e-6 | 100 % | 1 708 872 |
| 2 | 0.193342 | 0.581738 | 2.419e-6 | 100 % | 1 725 473 |

Toutes les sondes de conservation gardent 100 % de politique dans les
16 contextes. Aucun remplacement n'est admis sous bruit. Les trois reprises
ciblées reproduisent 1 024 futurs retours. Après changement, le contexte 0
atteint une sonde à 100 % à 2 000 retours/contexte pour la graine 0,
et à 4 000 pour les graines 1 et 2 ; les 15 autres contextes restent
corrects aux sondes. Les premières admissions arrivent autour de
1 174–1 180 retours ciblés et peuvent encore être partielles.

Le raffinement du même programme est proposé à 28 672, 28 672 et 24 576
retours globaux pour les graines 0/1/2. Il corrige le défaut de confiance
observé dans l'itération précédente, sans modifier le calibrateur ni
abaisser le seuil de Brier.

Ces 16 contextes partagent une règle commune avec une exception apprise.
Ils ne représentent pas 16 tâches indépendantes arbitraires.

## Coûts, reprise et précision

Le budget neuronal reste de 96 points S² après admission et 160 pendant
une validation, soit 192 et 320 degrés de liberté intrinsèques de l'espace
de paramètres. Cela ne prouve pas autant de directions indépendantes
effectivement utilisées par l'apprentissage. Aucun poids matriciel
euclidien appris n'est ajouté.

Deux gradients par retour et quatre passes de replay par banque restent
inchangés. Les moyennes géodésiques, contrôles statistiques, lectures pour
raffinement et recherches ajoutent du travail. Le mode de confiance
exécute encore la recherche habituelle avant d'imposer le programme courant ;
ce coût peut être simplifié ultérieurement.

Le gain de délai consomme davantage de tentatives dans les cas de bruit
initial : 103/106/105 contre 89/89/85 pour la référence. Les mises à jour
neuronales totales valent 998 656 / 1 023 232 / 1 015 040 contre
883 968 / 883 968 / 851 200, soit environ 13 à 19 % de plus.
Un délai en retours plus court ne signifie donc pas moins de calcul.

La montée à l'échelle garde au plus 4 096 lignes de fit, 4 096 probabilités
en cache, 16 recherches détaillées et un plafond de 112 décisions.
Le maximum observé à grande échelle est 26 décisions. Les compteurs et
archives à vie sont séparés. Les tailles JSON sont des tailles sérialisées,
pas des mesures de RAM totale. Les durées CPU par cas sont publiées ;
la RTX du PC de l'utilisateur n'a pas été utilisée.

Les décisions, programmes, supports et compteurs concordent entre systèmes.
Avec tolérances absolue et relative de 1e-10, tous les champs numériques
comparés concordent. Deux sommes V cumulées présentent environ 1,3e-10
d'écart absolu sur des valeurs de 24 261 et 33 809, soit moins de 6e-15
relatif ; leurs bornes et décisions ne changent pas. Ces écarts sont
conservés dans le fichier de comparaison, pas masqués.

Le risque à vie reste au plus 0,05 pour une création neuve, sous les
hypothèses du protocole. Les imports conservent les risques historiques
et les prévisions en attente. Les checkpoints sont strictement contrôlés,
sans constituer une preuve cryptographique de l'histoire.

## Itérations non retenues et limites

Les résumés des échecs sont publiés : remplacement possible de compétence
sous bruit variable ; délai de 18 000 après le contrôle du contexte ;
faux antipodes dus à l'arrondi ; Brier de récupération trop élevé à
grande échelle. Les seuils de compétence, bruit et récupération ont été
conservés. Le regard intermédiaire a augmenté le plafond du journal
de 96 à 112 décisions.

Les programmes restent limités à trois prédicats et les actions exploratoires
sont fournies uniformément par le protocole. Le modèle ne choisit pas encore
ses expériences ni ses objectifs. Le calcul symbolique de recherche et
les buffers sont une partie importante du système ; le nombre de points
neuraux ne résume pas sa capacité ni son coût.

Le dialogue, les objectifs autonomes, les agents coordonnés et les actions
dans les applications du PC restent à construire. Ces expériences ne
prouvent ni une intelligence générale, ni une nouveauté scientifique,
ni une supériorité de S² sur un réseau euclidien comparable.
