# Révision plastique sur S²

`PlasticRevisionLearner` et `PlasticRevisionAdapter` gardent les contrats
version 1 et la géométrie sphérique de la première pièce. L'identité est
`first_piece.plastic-revision-s2.v3`, le checkpoint neuronal est au format 8.

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
snapshot8 = PlasticRevisionAdapter.from_calibrated_checkpoint(snapshot5)
core = PlasticRevisionAdapter.restore(snapshot8)
```

Les méthodes `from_consolidated_checkpoint`,
`from_renewable_checkpoint` et `from_finite_checkpoint` suivent d'abord les
imports historiques. Une validation déjà commencée garde sa politique,
ses banques et ses horizons ; la nouvelle politique commence au prochain
essai. Une prévision en attente reste valable jusqu'au reçu ou à sa clôture.

L'import du format 7, ou du dernier prototype de format 6, est
`PlasticRevisionAdapter.from_plastic_revision_checkpoint(snapshot7)`
(avec `snapshot6` pour le format 6). Le cœur expose la même méthode.
Il préserve ses prévisions, banques, risques, compteurs, requêtes et
validations déjà commencées. Une restauration implicite d'un ancien format
est refusée. Un essai de confiance importé garde son journal de recherche
historique ; les nouveaux essais de confiance inscrivent zéro hypothèse
alternative examinée. Les
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

## Corrections et coûts d'intégration

Les [corrections prioritaires](PRIORITY_FIXES.md) contrôlent aussi le domaine
du logarithme du prototype transféré par rapport aux ancres de lecture.
Une moyenne inutilisable pour un gradient reçoit le prototype neutre,
même lorsque ses points sources étaient valides. La définition de S²,
les gradients, les seuils d'admission et le budget de replay sont conservés.

Un essai de confiance réajuste le programme protégé sans chercher de programme
alternatif. La préparation, les deux banques et la validation prospective
restent obligatoires. Le format 8 distingue ce travail réel dans son journal.

L'adaptateur copie seulement l'état modifiable par l'opération en cours.
Les observations partagent les banques en lecture ; les retours possèdent
leurs banques, leur contexte mutable et le journal de validation actif.
Un échec avant publication laisse le checkpoint précédent restaurable.

Le calcul d'un retour s'effectue hors du verrou des lectures. Les écritures
de reçus restent sérialisées ; un doublon attend la fin du premier calcul,
puis reçoit son accusé sans nouvel apprentissage. Pendant le calcul,
prévisions, métriques et checkpoints décrivent l'état précédent la publication.
L'API reste synchrone, à un flux et une action en attente.
Le calcul Python et le GIL ne donnent aucune garantie de latence.

`metrics(detailed=False)` omet les listes `searches` et `decisions` ;
les compteurs et budgets restent disponibles. Le comportement détaillé par
défaut et le checkpoint complet sont conservés. Le cache borné des lectures
géodésiques dépend des coordonnées, ancres et température ; il est dérivé,
non appris et non sérialisé.
