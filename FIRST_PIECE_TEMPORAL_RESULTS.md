# Résultats de la première pièce temporelle et révisable

La révision apprend une relation de premier ordre d'apparition et peut
la remplacer dans le même contexte observable, dans le laboratoire décrit
par le [protocole](FIRST_PIECE_TEMPORAL.md). Le réseau conserve des paramètres
et mises à jour sur S² et les mêmes contrats JSON que la première pièce.

Le commit testé est [`b9c38fe8a69f248b8665e6addc685cf84f6331be`](https://github.com/Setharkk/Remake-setharkk/commit/b9c38fe8a69f248b8665e6addc685cf84f6331be).
Les [tests et expériences](https://github.com/Setharkk/Remake-setharkk/actions/runs/37208231509)
et l'[évaluation finale indépendante](https://github.com/Setharkk/Remake-setharkk/actions/runs/37209018245)
réussissent sous Windows et Ubuntu, Python 3.11.

## Limites corrigées dans ce prototype

- L'ordre est désormais conservé en ligne ; des séquences aux mêmes
  présences peuvent produire des prédictions différentes.
- Un essai terminé ne bloque plus toute recherche future : les tentatives
  sont renouvelables dans un budget de 32 par contexte.
- Une relation devenue inadéquate peut être remplacée sans nouvel
  identifiant de tâche ni allocation structurelle supplémentaire.
- Une validation ne bloque plus l'apprentissage du modèle servi.
  Seuls le candidat et son contrôle restent figés.
- L'ordre partiel, les essais, les paramètres, les compteurs et les états
  aléatoires sont conservés par la reprise JSON.

`TemporalAdapter` annonce l'identité `first_piece.first-order-s2.v1`.
Les messages de prédictions, propositions et résultats restent en version 1.
Le checkpoint de présence est refusé explicitement, car il ne contient
pas l'ordre passé nécessaire à cette révision.

## Courbes d'acquisition

Cinq graines, 512 épisodes indépendants par horizon et par condition.
Les trois scénarios structurés partagent le même apprentissage initial ;
leurs lignes initiales ne sont donc pas trois réplications indépendantes.

| Interactions initiales | Succès avec ordre | Contrôle sans ordre | Brier avec ordre |
|---:|---:|---:|---:|
| 100 | 51.25 % | 51.25 % | 0.269616 |
| 1 000 | 48.55 % | 48.55 % | 0.273319 |
| 10 000 | 100 % | 49.22 % | 0.000001206 |

La relation 0-avant-1 est admise à 1 280 interactions sur les cinq graines.
La baisse à 1 000 ne démontrait pas une impossibilité : le candidat
n'avait pas encore été admis. Les 55 prédicats possibles sont programmés ;
l'indice utile est choisi depuis les résultats, pas donné au modèle.

## Changements cachés dans le même contexte

Le monde change après 10 000 interactions, sans transmettre la règle,
le couple ciblé, un numéro de régime ou une annonce du changement.
Un autre contexte stable est entraîné avant ce changement.

| Résultats appris après le changement | Inversion : succès | Nouvelle relation : succès |
|---:|---:|---:|
| 100 | 0 % | 49.96 % |
| 1 000 | 100 % | 49.96 % |
| 10 000 | 100 % | 100 % |

À 100, l'inversion provoque encore des décisions incorrectes, malgré
les mises à jour déjà en cours. Ce défaut précoce reste visible.

La récupération est sondée tous les 256 résultats, sur 128 épisodes
indépendants, avec succès >=0.95 et Brier <=0.02 :

| Graine | Inversion | Relation 0-avant-1 devenue 2-avant-3 |
|---:|---:|---:|
| 0 | 256 | 1 536 |
| 1 | 256 | 5 632 |
| 2 | 256 | 2 560 |
| 3 | 256 | 1 536 |
| 4 | 256 | 5 632 |

Ces nombres sont la première mesure satisfaisante, pas l'instant exact
de récupération. Dans l'inversion, les mêmes prototypes apprennent la
nouvelle sortie : aucune nouvelle relation n'est admise. Dans le changement
de relation, les cinq exécutions conservent finalement 2-avant-3 avec
exactement un remplacement et une seule allocation pour ce contexte.

Le remplacement reste lent pour certaines graines. Un candidat ancien
peut rester inconclusif jusqu'au dernier horizon ; les mises à jour
continuent, mais elles ne suffisent pas à inventer la nouvelle route
tant que la nouvelle distinction n'est pas admise.

## Défaut mesuré puis corrigé

La version [`9c0ddbdb91d3ab8e782e64f8e6ca6c9bdc622983`](https://github.com/Setharkk/Remake-setharkk/commit/9c0ddbdb91d3ab8e782e64f8e6ca6c9bdc622983)
figeait aussi le modèle utilisé pendant une comparaison.
Le [run 37207763620](https://github.com/Setharkk/Remake-setharkk/actions/runs/37207763620)
récupérait l'inversion seulement à 4 352 résultats sur les cinq graines.

Le modèle servi apprend désormais après chaque prédiction enregistrée.
Le candidat et son contrôle ne reçoivent pas les étiquettes de validation.
Avec les mêmes expositions et graines, la première mesure satisfaisante
passe à 256. Ce résultat concerne l'exposition en interactions, pas une
mesure de vitesse CPU ou une garantie de temps réel.

Le gain de la comparaison avec le modèle servi est une moyenne de
prédictions produites avant leurs résultats, dans le bloc passé.
La borne conditionnelle détaillée dans le protocole ne garantit pas que
le candidat sera meilleur que le modèle courant à tout instant futur.
Les évaluations réservées sont réalisées sans aucune mise à jour.

## Évaluation finale sur de nouvelles séquences

Après la correction, les checkpoints complets du run 37208231509
sont évalués avec de nouvelles graines de monde fixées dans
`validation/temporal_final_probe.py`, jamais utilisées pour repérer le défaut.
Aucun entraînement supplémentaire et aucune modification des états sources.

Par condition : 1 024 épisodes primaires par graine. Le transfert utilise
aussi 1 024 épisodes par graine avec de nouveaux distracteurs et de plus
longs délais. La rétention utilise 512 épisodes par graine pour le contexte
stable entraîné avant le changement.

| Condition finale | Modèle complet | Contrôle sans ordre | Référence de présence |
|---|---:|---:|---:|
| Ordre stationnaire | 100 % | 49.59 % | 49.59 % |
| Après inversion | 100 % | 50.27 % | 50.59 % |
| Après remplacement de relation | 100 % | 48.71 % | 50.08 % |
| Bruit indépendant | 50.06 % | 50.06 % | 50.06 % |
| Action seule | 100 % | 100 % | 100 % |

Le succès du modèle complet reste de 100 % sur les transferts structurés
et les deux conditions de rétention. La rétention conserve exactement
l'état stocké du contexte stable, avec des modèles séparés par contexte.

Effacer l'ordre dans un clone aux mêmes poids ramène le succès à
51.54 %, 49.77 % et 48.22 % respectivement dans les trois conditions
structurées. Cette intervention ne réentraîne pas un modèle sans mémoire.

Aucune relation n'est admise dans les cinq exécutions bruitées, malgré
11 à 19 tentatives par exécution à 10 000 résultats. Les cinq exécutions
« action seule » n'effectuent aucune tentative structurelle inutile.
Ces observations ne prouvent pas une absence de faux positifs sur tous
les mondes. Sur le bruit, le Brier final de 0.257259 reste moins bon
que 0.25 pour une prédiction constante à 0.5.

Le contrôle interne possède les mêmes quatre points S² par prédicteur
et reçoit autant de mises à jour que le modèle complet, y compris
les ajustements temporaires. L'ancien apprenant de présence a un autre
budget et une seule tentative : il sert de référence diagnostique,
pas de comparaison universelle à budget égal.

## Tests, coûts et reprise

**66 tests réussis par système**, dont 15 nouveaux tests temporels.
Ils couvrent l'ordre et les répétitions, les changements cachés,
les nouvelles tentatives après données bruitées, les plafonds,
la rétention, les erreurs sans mutation, les candidats figés avec
modèle servi apprenant, les checkpoints corrompus ou cycliques et
l'adaptateur commun.

La reprise JSON conserve une validation en cours et une mémoire d'ordre
partielle ; elle continue 64 interactions avec résultats et état final
identiques. Le test d'adaptateur reprend aussi une requête en attente,
refuse le mauvais format d'implémentation et déduplique ses résultats.

Pour l'expérience temporelle, par système :

| Coût mesuré | Quantité |
|---|---:|
| Interactions du contexte principal | 400 000 |
| Interactions du contexte stable supplémentaire | 20 000 |
| Mises à jour neuronales, contrôles et ajustements inclus | 897 856 |
| Épisodes d'évaluation principaux, transfert et rétention | 81 920 |
| Épisodes de sondage de récupération | 9 088 |
| Épisodes finaux indépendants supplémentaires | 46 080 |

Les actions de politique sont contrefactuelles dans le simulateur :
349 824 pour la première expérience avec ses sondes, puis 179 200 dans
l'évaluation finale. Elles ne sont pas des actions sur le PC ni des
retours supplémentaires entraînant le réseau.

Par contexte : 8 points S² actifs, contrôle inclus, soit 16 degrés de
liberté. Deux contextes actifs comptent donc 32 degrés de liberté.
Deux validations simultanées pourraient atteindre 32 points stockés
et 64 degrés de liberté. Le maximum échantillonné ici est de 24 points,
avec une seule validation en cours.

La mémoire d'épisode a 55 bits logiques. Les fenêtres de données et
les objets Python sont comptés séparément. Le plus grand checkpoint
de l'apprenant échantillonné vaut 308 702 octets sous Windows et
308 758 sous Linux ; ces tailles JSON ne sont pas une mesure de RSS
ni des copies temporaires de l'adaptateur.

Les temps écoulés publiés incluent évaluations et écritures.
Aucune performance de latence sur le PC NVIDIA de l'utilisateur n'est
déduite des machines GitHub Actions.

## Absence de régression et preuves

Le protocole de présence précédent est réexécuté. Par système, ses
4 241 valeurs numériques restent identiques à celles du run 37206180993,
en excluant les durées.

Entre systèmes, 18 555 valeurs temporelles sont comparées : écart maximal
1.07e-14, sous la tolérance de 1e-10, sans changement de décision.
Les durées et tailles JSON sont exclues de cette comparaison de valeurs.
L'évaluation finale compare 798 valeurs, avec écart maximal 2.22e-15.

Résultats conservés dans le dépôt :

- [Agrégats, courbes et comparaisons](first_piece_temporal_results/aggregate.json).
- [Expérience actuelle Windows](first_piece_temporal_results/run_37208231509/windows.json)
  et [Linux](first_piece_temporal_results/run_37208231509/linux.json).
- [Évaluation finale Windows](first_piece_temporal_results/run_37209018245/windows.json)
  et [Linux](first_piece_temporal_results/run_37209018245/linux.json).
- [Avant correction Windows](first_piece_temporal_results/run_37207763620/windows.json)
  et [Linux](first_piece_temporal_results/run_37207763620/linux.json).

Les artefacts du workflow contiennent les checkpoints complets,
l'environnement privé, le générateur des actions et les mesures déjà
atteintes. Les rapports ci-dessus restent accessibles après expiration
des artefacts. Le protocole peut être rejoué localement avec les commandes
de sa définition.

## Limites restantes

La grammaire ne connaît que la présence et le premier ordre d'apparition
dans un alphabet de dix symboles. Les répétitions, durées physiques,
comptages, relations longues et compositions générales restent hors de
cette grammaire.

Le seuil de déclenchement est heuristique et le remplacement peut
demander 5 632 résultats dans cette expérience. Le budget de vie est
32 tentatives par contexte ; son renouvellement statistique et durable
reste à concevoir. Le niveau alpha=0.05 porte sur une exécution configurée,
pas sur une famille unique regroupant tous les scénarios et graines.

La rétention mesure des modèles séparés, pas une mémoire neuronale
partagée. L'adaptateur garde un flux et une action en attente.
L'état se reprend par API, mais le benchmark n'a pas encore de commande
de continuation automatique d'une expérience interrompue.

Les objectifs autonomes, la planification, le dialogue et les actions
réelles restent à construire. Cette expérience ne démontre ni une
intelligence générale, ni l'originalité du mécanisme, ni un avantage
de S² sur une géométrie euclidienne.
