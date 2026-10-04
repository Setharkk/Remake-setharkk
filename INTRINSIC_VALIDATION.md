# Validation du réseau intrinsèque V1

La V1 remplace les poids euclidiens de la V0 par des positions neuronales
apprises sur l'hyperboloïde H4. Ses tests et son diagnostic d'apprentissage
ont été exécutés sous Windows et Linux le 4 octobre 2026.

Code testé : [401c9c7](https://github.com/Setharkk/Remake-setharkk/commit/401c9c75b6e2191115df3af19364fe3df8c076cb).
Exécution : [Cortex intrinsic network, 37167980219](https://github.com/Setharkk/Remake-setharkk/actions/runs/37167980219).

## Ce qui rend le réseau non euclidien

Chaque paramètre appris est un point p vérifiant <p,p>_L = -1 et p0 > 0.
Le réseau utilise des distances géodésiques entre prototypes, des centroïdes
de Lorentz et une connexion résiduelle par centroïde. Ses états intermédiaires
sont des points hyperboliques. Il ne contient aucune matrice nn.Linear apprise.

L'optimiseur convertit les gradients ambiants en gradients riemanniens,
calcule ses directions dans les espaces tangents, applique l'exponentielle,
puis transporte ses premiers moments au nouveau point. Son second moment
est scalaire par point et dépend de la norme riemannienne du gradient.

La métrique est celle de Lorentz, de courbure -1. Les cinq coordonnées
stockées représentent un point de dimension intrinsèque 4 : le fait de
les stocker dans un tenseur ne change pas la géométrie des paramètres.

Le budget est de 34 points, 136 degrés de liberté intrinsèques et
170 coordonnées stockées par modèle. L'ensemble comporte trois modèles :
408 degrés de liberté et 510 coordonnées. Ce sont des prédicteurs ;
la coordination d'agents reste à développer.

Les [formules et choix d'architecture](cortex_lab_v1/README.md) précisent
aussi la contrainte radiale de rayon 2.5. Cette contrainte privilégie
l'origine ; l'équivalence des mises à jour sous une isométrie est testée
lorsqu'elle est inactive.

## Vérifications exécutées

| Plateforme | Tests partagés V0 | Tests intrinsèques V1 | Diagnostic |
|---|---:|---:|---|
| Windows, Python 3.11.9 | 25 réussis | 10 réussis | 6 conditions terminées |
| Linux, Python 3.11.16 | 25 réussis | 10 réussis | 6 conditions terminées |

PyTorch 2.14.1+cpu, calcul en float64. Les runners utilisent le CPU ;
le GPU de l'utilisateur n'a pas été testé.

Les dix tests V1 vérifient les contraintes de tous les paramètres,
les états intermédiaires, les dérivées de la distance à des points confondus,
le transport parallèle, la tangence des moments après apprentissage,
la descente géométrique, l'invariance des sorties sous un boost de Lorentz
et l'équivalence de trois mises à jour dans deux repères. Ils vérifient
également l'absence de mutation partielle en cas de gradient non fini,
l'indépendance des instantanés et le rejet d'un instantané invalide.

Sur le test d'apprentissage, un modèle observe les 32 couples du laboratoire
et réalise 600 mises à jour. Son Brier passe de 0.265988 à 0.024693.
Il s'agit d'un test sur les couples d'entraînement, pas d'un résultat de
généralisation. Les positions changent et restent sur la variété :
l'erreur maximale de contrainte mesurée à la fin est 7.11e-15.

## Diagnostic sur des couples réservés

Commande exécutée :

~~~text
python -m cortex_lab_v1.run --steps 200 --seeds 0 1 2
~~~

Par graine, 24 couples état/action sont disponibles pour l'entraînement
et 8 sont réservés à l'évaluation, équilibrés entre les quatre actions.
Les résultats réservés n'entraînent pas le réseau. Les deux stratégies
utilisent les mêmes huit interactions initiales et le même ensemble
initial ; la sélection active emploie ensuite le gain d'information
avec 12 % de sélection aléatoire.

Chaque condition réalise 200 opérations sur des fichiers de laboratoire,
avec trois mises à jour par interaction et par modèle, soit 600 mises à jour
par modèle. Le total est de 1 200 interactions d'entraînement par plateforme.

Brier et NLL : plus bas est meilleur. L'exactitude exige les quatre bits
de résultat corrects. Valeurs Windows ; Linux diffère de moins de
5e-16 sur le Brier final.

| Graine | Sélection | Brier initial | Brier final | NLL finale | Exactitude finale |
|---:|---|---:|---:|---:|---:|
| 0 | active | 0.251239 | 0.185720 | 2.910923 | 50.0 % |
| 0 | random | 0.251239 | 0.143442 | 1.848916 | 50.0 % |
| 1 | active | 0.243977 | 0.210833 | 2.858931 | 25.0 % |
| 1 | random | 0.243977 | 0.194406 | 2.260402 | 25.0 % |
| 2 | active | 0.257525 | 0.205185 | 3.356285 | 37.5 % |
| 2 | random | 0.257525 | 0.200050 | 3.084355 | 25.0 % |

Le Brier initial moyen vaut 0.250914. Après 200 interactions, il vaut
0.200579 pour la sélection active et
0.179299 pour le hasard. Les six conditions
améliorent leur Brier par rapport à leur initialisation. L'erreur maximale
de contrainte des paramètres mesurée aux checkpoints vaut 7.11e-15.

Ces résultats restent fragiles. La sélection active fait moins bien
que le hasard en Brier pour chacune des trois graines. La NLL de la
sélection active se dégrade par rapport à l'initialisation dans les trois
cas : certaines erreurs deviennent plus confiantes. Plusieurs Brier
régressent après un checkpoint antérieur. L'apprentissage existe ;
sa progression monotone et la fiabilité de l'incertitude ne sont pas établies.

Trois graines et huit couples réservés issus d'un monde fermé de
32 couples ne constituent pas une validation d'un modèle du monde général.
Les V0 et V1 ont des architectures et budgets différents : ces scores
ne prouvent pas un avantage dû à la seule géométrie.

## Données et portée

Les [résultats Windows](benchmark_results/intrinsic_run_37167980219/results_windows.json)
et [résultats Linux](benchmark_results/intrinsic_run_37167980219/results_linux.json)
archivent les métriques initiales et finales ainsi que les résultats du test
d'apprentissage. Les artefacts de l'exécution contiennent aussi config.json,
splits.json, métriques intermédiaires, expériences, poids et mémoire.

La [spécification](SPEC.md) distingue les fonctions implémentées de celles
qui restent à construire : dialogue, choix de ses propres objectifs,
cortex coordonnant des agents, actions sur des applications et reprise
complète de l'apprentissage continu. La restauration des poids permet de
retrouver les prédictions dans un apprenant neuf ; elle ne restaure pas
l'optimiseur, la mémoire et les générateurs aléatoires.

Cette architecture repose sur des méthodes géométriques connues. Cette
validation ne revendique aucune innovation scientifique ni intelligence
autonome générale.
