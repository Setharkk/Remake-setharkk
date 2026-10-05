# Moteur de trace S² v2 : lecture calibrée, révision et service optionnel

Le v2 conserve l'encodeur récurrent sphérique du prototype et rend ses révisions de
poids et ses calculs accessibles par le contrat commun de la première pièce.
Ce module est un backend optionnel ; le service format 8 reste le défaut. Les
capacités des deux représentations ne sont pas interchangeables.

## Mathématiques et corrections

Pour un symbole opaque encodé par un point fixe e(s), l'état est mis à jour par
h' = Exp_h(0,75 Log_h(e(s))). La feuille est choisie par distance géodésique aux
centres appris. Les prototypes de sortie et les centres demeurent sur S².
Les sorties Bernoulli utilisent les distances aux ancres et les gradients
intrinsèques de SharedSpherePredictor. Il n'y a ni détecteur AAB/ABB fourni au
modèle, ni nombre de répétitions injecté dans les observations.

La confiance publiée est une lecture causale distincte des poids :
p_cal = b + λ(p_raw − b), b = moyenne des résultats observés,
λ = clip(Σ(p_i − b)y_i / Σ(p_i − b)², 10⁻⁶, 1).
Avec moins de 32 observations, ou une variance nulle, la lecture conserve la
probabilité brute. Les statistiques et leurs valeurs passées sont conservées
dans une fenêtre bornée par contexte et feuille ; seul un résultat observé
ajoute une ligne. Le contexte ne crée pas de nouveaux poids par lui-même.

La pente positive conserve l'ordre des actions dans cette formule. Quand un
bruit indépendant détruit leur pouvoir prédictif, la confiance revient vers le
taux observé ; les poids protégés ne subissent aucun gradient. Après une
admission, les calibrations sont reconstruites à partir du passé déjà observé.
Cette mémoire de résultats n'est pas une estimation d'incertitude épistémique.

Une proposition entraîne ses banques sur le passé. Les poids, centres et routes
du candidat sont figés pendant sa validation. Ses calibrations continuent à
utiliser uniquement les labels antérieurs à chaque prévision.
Une subdivision doit battre la référence calibrée réellement servie et un contrôle
de routage aléatoire. Une révision locale doit battre la référence calibrée et
recevoir des observations des deux actions. Demander une supériorité sur le contrôle
aléatoire empêcherait de réviser une règle constante dans une feuille.

Les horizons sont 128, 512, 2 048 et 8 192 observations futures de la feuille.
L'essai j dépense α_j = 0,05/[j(j+1)] ; ce compteur ne redémarre pas après une
restauration. La borne utilise la largeur 2 log(99) des gains de log-probabilité
tronquée, les comparaisons et les horizons déclarés. Elle correspond à un test
conditionnel de gains moyens bornés, pas à une garantie de stationnarité du monde.
Une calibration ou un essai clos sans admission ne remplace pas les poids.

Les délais de vérification sont séparés par feuille. Un délai global appliqué
après chaque vérification, même sans proposition, pouvait toujours retomber sur
la même feuille avec des observations alternées et affamer une autre révision.

## Utilisation et connexion aux pièces suivantes

~~~python
from first_piece.trace_service import AdaptiveTraceService

service = AdaptiveTraceService(seed=0, minimum_observations=32)
service.capabilities()
# Messages JSON version 1, identiques au contrat des adaptateurs de flux :
# stream.symbol : payload {"value": "symbole opaque"}
# stream.end    : payload {"value": "sealed"}
prediction = service.submit_observation(observation)
request = service.register_action(proposal, executor_id="executor:local")
service.begin_receipt(receipt)
while service.work_status()["state"] == "working":
    status = service.advance(max_units=128)

snapshot = service.checkpoint()
restored = AdaptiveTraceService.restore(snapshot)
~~~

Le coordinateur choisit le backend après lecture de ses capacités. Les messages,
identités de prévisions, actions et reçus, la révision et la déduplication gardent
le contrat version 1. La continuation est first_piece.trace-cooperative.v2.
Le checkpoint de service garde son enveloppe format 1 ; celui du moteur est
format 2, avec l'identité first_piece.adaptive-trace-s2.v2.

Les observations sont traitées sur une copie des champs qu'elles peuvent écrire.
Un reçu entraîne une copie privée du modèle. Le modèle et son accusé sont publiés
ensemble après calcul complet. Une pause garde la prévision et le modèle précédents.
Une exception remet le travail privé à l'état servi en gardant le même reçu.
Le service n'exécute aucun effet PC ; l'exécuteur doit conserver son journal durable.

Un quota compte des blocs de huit lignes de géométrie, des gradients unitaires ou
des opérations administratives bornées. Initialisation, shuffle, reconstruction
des calibrations et publication restent atomiques ; aucune latence maximale en
millisecondes n'est promise. La copie de begin_receipt, les checkpoints,
la restauration et la sérialisation JSON restent hors du quota d'advance.
La partition et le replay possèdent des curseurs
persistés et peuvent reprendre après JSON à toutes leurs phases.

coverage() compte les résultats réellement observés dans la feuille et le contexte
de la prévision courante, par action. Les rejouages et doublons n'augmentent pas ces
nombres. Une couverture élevée ne constitue pas un intervalle épistémique.

## Limites et décisions de compatibilité

* Deux actions binaires, huit contextes, 64 symboles ; les autres capacités sont
  annoncées et contrôlées avant ingestion. Pas d'extension arbitraire des plafonds.
* Fenêtre de replay ≤ 256 ; calibration ≤ 256 observations par contexte.
  Les feuilles, leurs prototypes et leurs centres sont bornés à huit feuilles et
  profondeur quatre. La suppression/fusion de feuilles reste à concevoir.
* La représentation récurrente, la partition et l'opérateur de révision sont fournis.
  Le système ne crée pas de nouveaux opérateurs, objectifs, agents ou langage.
* Les poids sont partagés entre contextes d'une même feuille. La calibration ne
  résout pas automatiquement des règles opposées propres à différents contextes.
* Des résultats synthétiques positifs ne prouvent ni une capacité générale de world
  model, ni une supériorité de S². Une comparaison à un réseau fixe utilisant le même
  état récurrent reste nécessaire pour isoler l'intérêt de la croissance.
* Les checksums de continuation détectent une altération accidentelle ; ils ne
  prouvent ni l'origine du checkpoint ni l'absence de falsification de l'historique.
* Le format 8 continue à utiliser son propre service. Sa mémoire ne contient pas
  l'ordre/multiplicité requis pour reconstruire cette trace. Aucun import implicite
  n'invente ces informations. Le v1 est conservé comme référence reproductible ;
  il n'est pas le moteur du service v2.

Le [protocole fixé avant mesure](FIRST_PIECE_TRACE_V2_PROTOCOL.md) et le
[rapport de résultats](FIRST_PIECE_TRACE_V2_RESULTS.md) séparent les tests
d'ingénierie des critères de recherche et conservent les échecs observés.
