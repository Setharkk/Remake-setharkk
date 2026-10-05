# Première pièce : calcul reprenable et représentation adaptative

Référence gelée : `9dbc2876d8347667dd46deddd9f340be96640c4d`,
moteur plastique neuronal de format 8. Ce protocole est fixé avant mesures.

## Contrat pour le cortex

Une autorité, un flux, une action en attente. Les observations, propositions,
requêtes et reçus gardent les contrats JSON version 1. Le service coopératif
ajoute un protocole de travail séparé : `begin_receipt`, `advance(max_units)`,
`work_status`, `coverage`, `checkpoint` et `restore`.
La prévision et la révision précédentes restent servies jusqu'à la publication.
Un doublon de reçu ne crée pas d'autre apprentissage. Un reçu contradictoire
est refusé. Le service ne réalise aucune action PC et n'écrit pas sur disque.

Le checkpoint du service enveloppe le checkpoint de l'adaptateur et le travail
en cours. Une reprise conserve ordre de replay, RNG, banques partielles et
curseurs. Le checksum détecte une altération accidentelle ; il ne prouve pas
l'histoire. Le coordinateur doit persister cet état et son journal d'exécution.

Une unité est une opération déclarée : un bloc de huit lignes d'index,
une hypothèse, un gradient, un mélange de lignes, ou une phase administrative.
Ce quota n'est pas une garantie de millisecondes. Initialisation géodésique,
tri du pool, calibration et publication ont des coûts atomiques bornés par
les capacités annoncées. Le rapport mesure aussi les pics de temps observés.

## Critères d'ingénierie

- Prévisions, programmes, poids, RNG et compteurs identiques au format 8
  synchrone, sauf durées de recherche.
- Au plus le quota annoncé par appel ; pausing à chaque phase, JSON et
  reprise produisent le même état final sans nouveau gradient consommé.
- Reprises pendant recherche, replay candidat/contrôle et entre passes.
- Lectures avant publication cohérentes, erreur et doublons sans mutation
  du modèle servi.
- Couverture = lignes récentes réellement étiquetées, pour chaque action
  et route du programme servi. Aucune duplication par les passes de fit.
  Statuts non observé / peu observé / observé au seuil configurable (32 par
  défaut). Ce seuil ne certifie ni généralisation ni incertitude épistémique.
- Comparaison directe / service sur 32000 retours, 64 symboles et 16 contextes,
  plus fit complet à 4096 lignes avec quota 128.

## Expérience de représentation

Les événements sont identiques pour toutes les variantes. Un préfixe contient
les deux marqueurs et des distracteurs opaques, puis trois événements AAB
ou ABB. Le préfixe, la présence, le premier ordre et la longueur sont appariés
entre les deux résultats. La première pièce actuelle ne mémorise pas leurs
multiplicités. Les actions 0/1 sont uniformes et le résultat observé est
1 si l'action choisie correspond au type de séquence. Aucune identité cible
n'entre dans les apprenants.

Le prototype encode chaque événement avec une relaxation géodésique :
`h(t+1)=Exp_h(t)(0.75 Log_h(t)(e(symbole)))`.
Les codes fixes `e` sont des points S² issus d'un hash opaque, sans label.
Ils sont des constantes d'observation, pas des poids appris.

Une feuille prédit avec des prototypes S² mis à jour par gradients tangents.
Une erreur persistante peut proposer deux centres S² depuis les états
observés, par clustering géodésique, puis ajuster deux banques à partir du
passé. Les centres, banques et référence sont figés pendant une validation
sur de nouveaux résultats. Une séparation n'est publiée qu'après un gain
prospectif borné. La mémoire protégée ne reçoit pas de gradients.

Comparaisons : format 8, même encodeur sans séparation, encodeur adaptatif.
L'encodeur et l'opérateur de séparation sont fournis par le code : l'expérience
ne démontre pas l'invention libre d'opérateurs ou d'une géométrie.
Elle mesure une allocation de représentation décidée depuis les données.

Graines 0/1/2, actions et épisodes appariés. Par graine : 2048 résultats
indépendants, 16384 structurés, 8192 indépendants puis 4096 de récupération.
Courbes à 512/2048/8192/16384 résultats de signal. Sondes sans apprentissage
sur 512 épisodes, puis 512 avec préfixes plus longs (distracteurs 9..12,
contre 2..7 en apprentissage) et un contexte neuf. Les trois premiers
horizons ne remplacent pas l'exposition complète.

Critères du prototype : aucune séparation admise sous bruit, >=95% de
politique finale et sur préfixes plus longs/contexte neuf, conservation
>=95% pendant bruit, reprise JSON exacte. Risque à vie de proposition
alpha(j)=0.05/[j(j+1)], partagé sur trois regards 128/512/2048.
Gain tronqué à [0.01,0.99], borne de Hoeffding bilatérale avec largeur
2 log(99) ; seuil de gain 0.01, support >=16 par enfant et >=8 par action/enfant.
Maximum 8 feuilles, 256 épisodes retenus par feuille, profondeur 4.
Les maxima de points, lignes, durées et octets JSON sont publiés.

Un échec demeure un résultat. Les seuils ne sont pas abaissés après mesures.
Les budgets fixes subsistent ; un petit test positif ne prouve pas une
intelligence générale ni un avantage de S² sur une géométrie euclidienne.
