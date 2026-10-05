# Catalogue d'actions configurable : première pièce S²

Le backend optionnel `ActionTraceService` accepte un catalogue de N actions nommé à la construction.
Il remplace le plafond de deux actions du moteur de trace et celui de seize
de la banque partagée par des budgets de ressources contrôlés avant allocation.
La liste est fixe pour la vie du modèle ; les actions ont encore des arguments
vides et un résultat Bernoulli `lab.success/binary`.

~~~python
from first_piece.action_service import ActionTraceService

service = ActionTraceService(
    actions=tuple(f"operation:{i}" for i in range(32)),
    seed=0,
)
print(service.capabilities())
~~~

Il expose les observations, prévisions, réservations d'actions, reçus,
`begin_receipt`, `advance`, `coverage`, `checkpoint` et `restore`
des services précédents. La couverture compte les résultats effectivement
observés dans la feuille et le contexte actuels ; le replay ne crée pas de
nouveaux exemples observés. Une continuation garde le modèle servi inchangé
jusqu'à publication complète du reçu. Le quota compte des unités de travail,
sans garantir un temps maximal en millisecondes.

## Formules et ressources

Chaque sortie possède un point appris sur S². Le nombre d'actions ne détermine
ni le nombre de branches géodésiques ni la valeur binaire du résultat.
L'encodeur, la récurrence par exp/log riemanniens, le partitionnement géodésique,
le replay intrinsèque, les poids protégés et la lecture calibrée sont conservés.

Pour N actions : fenêtre W=128N, minimum de fit=64N,
calibration C=max(256,64N), horizons (128,512,2048,8192)×ceil(N/2).
Le constructeur réserve N(8L+2)+2L points et (L+3)W+4TC lignes,
où L est le nombre maximal de feuilles et T celui des contextes.
Les budgets par défaut sont 65 536 points et 131 072 lignes.

Ces lignes constituent une réserve algorithmique, pas une limite de RAM en
octets : les objets Python, l'exécuteur et les copies de checkpoints ajoutent
leur coût. Une demande dépassant le budget est refusée avant allocation des
banques. Augmenter le budget ou réduire les contextes/feuilles est explicite :

~~~python
service = ActionTraceService(
    actions=tuple(f"operation:{i}" for i in range(128)),
    learner_options={"max_tasks": 1, "max_leaves": 2},
)
~~~

Cet exemple est vérifié pour la construction, la prévision et la reprise.
Il ne constitue pas une démonstration d'apprentissage à 128 actions.

Le déclencheur Brier et le gain minimal sont divisés par N/2 afin de ne pas
diluer une amélioration portant sur une seule action. La validation future
utilise les largeurs de gains calculées avant les labels et une grille
exponentielle déclarée, avec risque sommable à vie. Une révision exige aussi
la confirmation future des changements de direction des actions concernées.
Le [protocole](ACTION_CATALOGUE_PROTOCOL.md) décrit les hypothèses et critères ;
le [rapport](ACTION_CATALOGUE_RESULTS.md) contient les mesures et les échecs.

## Reprise et compatibilité

Identité neuronale : `first_piece.action-trace-s2.v3`, format 3.
Continuation : `first_piece.action-cooperative.v3`.
Les messages JSON gardent leur version 1.

`ActionTraceLearner.from_v2`, `ActionTraceAdapter.from_v2` et `ActionTraceService.from_v2`
importent explicitement les anciens états. Une prévision et une requête déjà
annoncées gardent leurs identités et valeurs. Un essai v2 en cours conserve
sa politique statistique jusqu'à sa clôture ; les essais suivants utilisent
la nouvelle politique. Un fit partiellement exécuté reprend son candidat,
son ordre de replay et son RNG.

Le moteur format 8 reste le backend par défaut, et le moteur de trace v2
reste restaurable. Agrandir un catalogue déjà entraîné n'est pas une migration
fournie : il faut créer un modèle avec son catalogue déclaré.

## Reproduire

~~~text
python -m unittest discover -s first_piece/tests -v
python -m validation.action_probe --out actions.json
~~~

La sonde complète teste 4, 8 et 32 actions sur trois graines, avec deux familles
de récompenses, du bruit, une reprise et une inversion. `--quick`
exécute seulement la comparaison directe/service sur 8 192 résultats par catalogue.

Les coûts de prévision et l'exploration augmentent avec N. Huit contextes,
64 symboles, huit feuilles, quatre niveaux, un flux et une action en attente
restent des limites distinctes. Les actions paramétrées, leur création dynamique,
les objectifs, le dialogue, les exécuteurs PC et une supériorité démontrée de S²
restent à construire ou à établir.
