# Service coopératif de la première pièce

Le cœur reste le moteur neuronal S² plastique de format 8.
`CooperativeService` ajoute une continuation de calcul et une couverture
des résultats observés. Son checkpoint est une enveloppe versionnée distincte ;
il ne remplace pas le format du moteur ni les messages JSON version 1.

## Utilisation par la pièce suivante

`submit_observation` reçoit les événements ordonnés.
`register_action` réserve une seule action pour l'exécuteur désigné.
Le coordinateur conserve sa requête et son journal d'exécution. Une fois le
résultat connu, il appelle `begin_receipt(receipt)`, puis
`advance(max_units=128)` jusqu'à l'état `completed`.
Le retour contient le nombre d'unités consommées et l'accusé final.
La révision ne change qu'après publication du modèle complet.

~~~python
from first_piece.cooperative import CooperativeService

service = CooperativeService(seed=0)
# prediction = service.submit_observation(message)
# request = service.register_action(proposal, executor_id="pc.executor")
# receipt doit correspondre à une action déjà exécutée et mesurée.
status = service.begin_receipt(receipt)
while status["state"] != "completed":
    status = service.advance(128)
ack = status["ack"]
~~~

`submit_receipt` est aussi disponible comme chemin synchrone compatible.
`coverage(prediction_id)` détaille pour la prévision active le nombre de
résultats récents par action et route, le nombre positif et un statut :
non observé, peu observé, observé. Le seuil par défaut est 32, configurable
de 1 à 1024. Ce statut ne certifie ni généralisation ni intervalle épistémique.
Le replay ne compte pas comme de nouvelles observations.

## Pause et reprise

Une exception dans une unité de calcul abandonne uniquement les modifications
privées et reconstruit le travail depuis le modèle servi, avec le même reçu.
L'erreur est propagée au coordinateur ; sa reprise peut recalculer les gradients
non publiés, sans réexécuter l'action ni apprendre deux fois le résultat.
Une erreur lors de la publication conserve le calcul terminé pour un nouvel essai.

Le coordinateur peut interrompre les appels à `advance` entre deux quotas.
`checkpoint()` conserve ensemble l'état servi, l'action en attente,
le reçu, les curseurs de recherche, la permutation de replay, les banques
partiellement ajustées et les générateurs aléatoires. Après un aller-retour
JSON, `CooperativeService.restore(snapshot)` reprend le calcul sans
réexécuter l'action ni rejouer les gradients déjà consommés.

Les checkpoints du cœur et du service sont deux objets différents :
restaurer un checkpoint du service avec `PlasticRevisionAdapter.restore`
est incorrect. Importer les anciens formats se fait d'abord par les
fonctions d'import explicites de l'adaptateur ; le service utilise ensuite
cet adaptateur validé avec
`CooperativeService.from_adapter_checkpoint(snapshot)`. Ce passage conserve
le modèle et une éventuelle action en attente.

Un checksum protège la continuation contre une altération accidentelle.
Il ne constitue ni une signature ni une preuve de l'historique d'exécution.
Le coordinateur doit écrire son checkpoint de façon atomique et gérer les
effets réels de l'exécuteur. Un reçu oublié hors de la fenêtre de déduplication
n'est pas une garantie globale d'exécution exactement une fois.

## Contrat et limites

Une seule autorité apprend, un seul flux est ordonné et une seule action
est en attente. Des agents proposeront des actions à cette autorité ;
ils ne posséderont pas des copies concurrentes du même cœur à fusionner.
L'état servi reste cohérent pendant un travail incomplet. Les nouvelles
observations attendent la résolution de l'action ; ce service ne permet pas
encore plusieurs transitions en vol.

Le quota compte des primitives bornées : huit lignes d'index, une
hypothèse, un gradient, un mélange ou une phase administrative.
Il n'impose pas une durée maximale en millisecondes. Initialisation
géodésique, tri, calibration et publication restent des phases atomiques
dont le coût dépend des capacités déclarées. La durée de restauration et
de sérialisation n'est pas incluse dans le quota.

Le service ne contient ni ordonnanceur système, ni processus d'agents,
ni accès aux applications, ni persistance automatique. Il prépare le
contrat du cortex ; ces responsabilités appartiennent à la prochaine pièce.

Le protocole et les résultats sont disponibles dans
[FIRST_PIECE_READINESS_PROTOCOL.md](FIRST_PIECE_READINESS_PROTOCOL.md) et
[FIRST_PIECE_READINESS_RESULTS.md](FIRST_PIECE_READINESS_RESULTS.md).
L'expérience `AdaptiveTraceLearner` est un module distinct :
elle ne remplace pas le moteur servi tant que son contrat d'intégration et
ses capacités n'ont pas été validés pour ce rôle.
