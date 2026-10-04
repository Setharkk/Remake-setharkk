# Révision plastique sur S²

`PlasticRevisionLearner` et `PlasticRevisionAdapter` gardent les contrats
version 1 et la géométrie sphérique de la première pièce. L'identité est
`first_piece.plastic-revision-s2.v2`, le checkpoint neuronal est au format 7.

## Utilisation et imports

```python
from first_piece.plastic_revision_adapter import PlasticRevisionAdapter

core = PlasticRevisionAdapter(actions=("a", "b", "c", "d"))
# submit_observation, register_action et submit_receipt suivent
# les mêmes contrats que CalibratedAdapter.
snapshot = core.checkpoint()
resumed = PlasticRevisionAdapter.restore(snapshot)
```

Une seule prévision et une seule action restent en attente. Un reçu déjà
traité ne produit pas un second apprentissage. Les agents futurs partagent
cette autorité ; ils n'ont pas chacun un réseau et un compteur indépendants.

L'import de l'ancien mode doit être explicite :

```python
snapshot7 = PlasticRevisionAdapter.from_calibrated_checkpoint(snapshot5)
core = PlasticRevisionAdapter.restore(snapshot7)
```

Les méthodes `from_consolidated_checkpoint`,
`from_renewable_checkpoint` et `from_finite_checkpoint` suivent d'abord les
imports historiques. Une validation déjà commencée garde sa politique,
ses banques et ses horizons ; la nouvelle politique commence au prochain
essai. Une prévision en attente reste valable jusqu'au reçu ou à sa clôture.

L'import du dernier prototype de format 6 est
`PlasticRevisionAdapter.from_plastic_revision_checkpoint(snapshot6)`.
Il préserve ses prévisions, banques et validations déjà commencées. Les
premières versions expérimentales ayant moins de regards ou de sommes V
restent associées à leur code historique.

## Calculs et budgets

Le [protocole](PLASTIC_REVISION_PROTOCOL.md) donne les formules du transfert,
du test de fit, des sommes de largeurs conditionnelles et des quatre
réglages exponentiels. Les paramètres neuronaux restent des points de S².
Les moyennes utilisent log et exp géodésiques, sans matrice euclidienne apprise.

Le transfert peut être refusé prototype par prototype. Les compteurs
d'optimiseur du candidat repartent à zéro ; les banques sources continuent
à apprendre. Quatre passes de replay restent quatre passes : la recherche,
les moyennes et le calibrateur ajoutent des calculs distincts.

Avant la première admission, une référence plastique figée sert pendant
la validation. Ensuite la compétence consolidée sert de référence.
Les examens d'un candidat dépassé à 512 ou 1 024 retours peuvent clore un
essai encore en attente, sans admission ni remboursement du risque statistique.
Le prochain essai consomme un budget neuf et valide sur ses labels futurs.

Avec quatre actions et huit routes : 96 points après admission, 160
au maximum pendant un essai, soit 192 et 320 degrés de liberté intrinsèques.
Ces degrés de liberté décrivent la dimension de l'espace de paramètres,
avec ses contraintes. Ils ne prouvent pas autant de directions indépendantes
utilisées par l'apprentissage, ni un avantage de cette géométrie.
Le cache probabiliste et les buffers ne sont pas des poids neuronaux.
Le nombre de contextes et de symboles augmente leurs coûts.

Les métriques publient les tentatives à vie, le risque, les archives,
les points alloués, la référence de validation et le compteur de remplacements
de candidats `supersessions`. `plastic_initialization_searches` concerne
le bloc détaillé courant. Les anciens compteurs d'archive « inconclusive »
incluent les essais « superseded » ; `archived_supersessions` en donne
le sous-total exact.

Le risque à vie vaut au plus 0,05 pour une création neuve. Un import
depuis le mode fini peut conserver le budget historique supplémentaire
décrit dans [RENEWABLE_SEARCH.md](RENEWABLE_SEARCH.md).
Ce risque gouverne les admissions sous les hypothèses du protocole.
Il ne garantit ni le calibrateur adaptatif, ni une compétence générale.

## Mesures et portée

Les [résultats](PLASTIC_REVISION_RESULTS.md) publient la comparaison,
les ablations, les reprises Windows/Linux et les coûts de montée à l'échelle.
Ils distinguent la première admission d'une compétence correcte dans
tous les contextes.

Le dialogue, la sélection d'objectifs, l'exploration apprise et l'exécution
dans les applications du PC restent à construire. Les expériences sont
synthétiques ; aucune supériorité sur un réseau euclidien n'est établie.
