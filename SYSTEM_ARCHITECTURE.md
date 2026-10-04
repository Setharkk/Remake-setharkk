# Architecture commune et frontières des pièces

Les interfaces sont définies avant d'étendre l'apprenant. Elles empêchent
les futurs agents de dépendre des numéros de tâches, du masque de présence,
des coordonnées S² ou des deux actions du laboratoire. Elles ne garantissent
pas l'absence de toute évolution de l'architecture.

## Responsabilités

| Pièce | Responsabilité | État |
|---|---|---|
| Contrats communs, `setharkk/contracts.py` | Messages JSON versionnés, identités, ordre logique, unités | Implémentés, version 1 |
| Adaptateurs, `FirstPieceAdapter` et `TemporalAdapter` | Traduire les mêmes messages vers l'apprenant choisi ; conserver sa frontière de reprise | Implémentés, un flux et une action en attente |
| Première pièce neuronale | Mémoire d'événements, prédictions et modification des prototypes S² | Présence et premiers ordres d'apparition ; tentatives et remplacement bornés |
| Cortex coordinateur | Arbitrage des propositions, ressources communes, priorités, journal durable | À construire ; l'adaptateur possède déjà une seule autorité d'apprentissage |
| Objectifs et planification | Distinguer la demande utilisateur, les objectifs exploratoires et leur valeur | À construire ; un `goal_id` peut déjà accompagner une proposition |
| Agents | Consulter les prédictions et proposer une action au coordinateur | Agents simulés dans le test ; essaim autonome à construire |
| Capteurs et exécuteurs PC | Traduire les observations et exécuter les actions retenues | Monde synthétique seulement ; applications réelles à construire |
| Dialogue | Transformer une demande en objectif et expliquer les résultats | À construire |

~~~mermaid
flowchart LR
    S[Capteurs] -->|observation ordonnée| C[Cortex coordinateur]
    C --> M[Première pièce neuronale]
    M -->|prédiction versionnée| C
    C --> A[Agents et objectifs]
    A -->|proposition| C
    C -->|requête choisie| E[Exécuteur]
    E -->|résultat corrélé| C
    C -->|résultat observé| M
~~~

Le schéma décrit la cible. L'implémentation actuelle couvre les messages,
la frontière de la première pièce et une boucle synthétique de vérification.

Les agents sont des extensions du même système : ils lisent des copies de
prédictions et proposent des expériences. Ils ne possèdent pas chacun un
apprenant indépendant dont les poids divergeraient. Un verrou protège la
mutation locale. Le coordinateur futur décidera quelle proposition exécuter ;
l'adaptateur actuel refuse une seconde action différente en attente.

## Contrats version 1

Tous les messages portent `schema_version=1`. Les validateurs renvoient
des copies détachées et refusent les champs supplémentaires, les versions
inconnues, les cycles, les valeurs non JSON et les nombres non finis.
Les identifiants sont des chaînes opaques. Les compteurs entiers sont
bornés à 2^53-1 pour conserver leur sens entre langages.

| Message | Informations communes |
|---|---|
| Observation | `event_id, stream_id, sequence, context_id, source_id, kind, payload` |
| Prédiction | `prediction_id, model_id, model_revision`, événement et contexte d'origine, liste de prévisions |
| Prévision d'un candidat | `candidate_id, action_name, arguments, measure, unit, distribution` |
| Proposition d'agent | `agent_id, goal_id, prediction_id, model_revision, candidate_id` |
| Requête d'exécution | `request_id`, modèle et prédiction, contexte et séquence, agent, objectif, exécuteur désigné, candidat et opération |
| Résultat d'exécution | `receipt_id, request_id, source_id, status, outcome` |

Deux candidats peuvent partager un nom d'opération avec des arguments
différents. Le coordinateur lie la proposition au candidat effectivement
évalué ; un agent ne peut pas substituer une opération derrière la prédiction.

Une distribution contient `kind` et `parameters`. La loi Bernoulli est
validée numériquement. D'autres lois sont transportables, mais leurs
paramètres doivent être validés par les producteurs et consommateurs qui
les comprennent. Leur simple acceptation structurelle n'est pas une preuve
de validité statistique. L'apprenant actuel annonce uniquement Bernoulli.

`sequence` exprime l'ordre logique au sein d'un flux, pas une durée physique.
Le producteur attribue des identités cohérentes. L'adaptateur exige les
séquences consécutives à partir de zéro et refuse les événements d'un autre
flux. Seule la répétition exacte du dernier événement reçoit son ancien
accusé sans nouvelle consommation. Les reprises d'événements plus anciens
demandent un journal futur ; elles sont refusées actuellement.

`context_id` est un contexte observable, pas l'identité d'une règle cachée.
Il reste identique si la règle de ce contexte change. L'adaptateur utilise
une table bornée de contextes vers les tâches internes et refuse le dépassement.
Il n'invente pas une nouvelle tâche pour absorber une contradiction.

## Apprentissage, prédiction et objectifs

`model_revision` compte les résultats effectivement appris, y compris
l'interaction qui admet une distinction. Les agents associent leur choix à
la prédiction et à sa révision. Une proposition ancienne ou étrangère est
refusée. Les types internes de mémoire ou de réseau n'apparaissent pas
dans ces échanges.

Une prédiction du résultat d'une action n'est pas la valeur d'un objectif.
Les mesures portent leurs unités ; leur interprétation par un objectif
appartient au futur planificateur. `goal_id` est seulement une référence :
il ne crée pas encore de génération ou d'évaluation autonome de buts.
La probabilité Bernoulli ne représente pas à elle seule une confiance
épistémique ; l'adaptateur annonce que celle-ci n'est pas estimée.

Les propositions actuelles choisissent parmi les candidats déjà évalués.
La génération de nouveaux candidats, leur évaluation et les plans à
plusieurs étapes restent à construire. Une distribution inconnue ne doit
jamais devenir silencieusement une probabilité de succès arbitraire.

Un résultat `observed` contient une mesure, une unité et une valeur.
Les statuts `failed` et `cancelled` ferment l'épisode sans entraîner le
réseau : une panne d'exécution n'est pas un exemple négatif inventé.
Dans ce modèle, seul un résultat entier 0 ou 1 pour `lab.success/binary`
est accepté. Un autre modèle devra annoncer et valider ses propres mesures.

## Frontière de reprise et répétitions

Le checkpoint de l'adaptateur conserve :
le modèle et son état aléatoire, les correspondances de contextes,
l'ordre des observations, la prédiction en attente, la requête sélectionnée,
la révision et un cache borné des résultats terminés.

Il porte un format, une version de contrat et l'identifiant
`first_piece.presence-s2.v1`. Une incompatibilité est refusée. L'apprenant temporel utilise déjà l'identité distincte
`first_piece.first-order-s2.v1` et refuse la conversion implicite ; un ancien masque de présence ne reconstitue pas
un ordre passé qui n'a pas été enregistré.

Une même requête terminée avec le même résultat reçoit le même accusé,
même sous un nouveau `receipt_id`, sans nouvel apprentissage. Un résultat
contradictoire est refusé. Le cache vaut 64 entrées par défaut ; après
éviction, une ancienne requête est refusée, jamais attribuée à une nouvelle
action. Un accusé d'observation répété reste historique : il ne recrée pas
une prédiction active après le traitement de son résultat.

Cela protège les mises à jour du modèle dans cette frontière locale.
Cela ne garantit pas une exécution physique unique après panne du PC.
Avant toute action réelle, l'exécuteur et le coordinateur devront conserver
durablement les intentions et résultats, puis résoudre le cas « action
réalisée, résultat pas encore enregistré ». Ils ne doivent pas réexécuter
aveuglément une action en retrouvant une requête en attente.

L'état n'est pas écrit automatiquement sur disque par l'adaptateur.
L'appelant doit sauvegarder un checkpoint cohérent et le journal correspondant.
Les transactions utilisent actuellement une copie temporaire du petit
apprenant. Ce coût CPU et mémoire convient à la vérification du prototype ;
il devra être mesuré et remplacé si le cortex grandit.

## Limites locales et travaux à leur bonne place

| Limite | Où la résoudre | Condition avant l'étape dépendante |
|---|---|---|
| Relations temporelles arbitraires et budget de tentatives renouvelable | Première pièce | [Révision bornée disponible](FIRST_PIECE_TEMPORAL.md), famille et budgets plus généraux à mesurer |
| Réseaux séparés par tâche | Première pièce puis mémoire commune | Mesurer l'interférence avant de revendiquer une mémoire neuronale partagée |
| Un flux, une action en attente | Coordinateur et états de continuation | Ordonnancement borné, corrélation des résultats et reprise testés avant agents parallèles |
| Budgets de validation temporaires | Première pièce et coordinateur | Compter aussi les candidats, données, essais et coûts d'évaluation |
| Pas de journal d'exécution durable | Coordinateur et exécuteur | Reprise après interruption avant actions réelles |
| Valeur des objectifs et choix des expériences | Objectifs/planification | Critères explicites, comparaisons et horizons déclarés |
| Pas de dialogue ni de capteurs PC | Adapteurs spécialisés et dialogue | Respecter les contrats ; annoncer les capacités réellement acceptées |

Les deux actions, les dix symboles et les deux contextes par défaut sont
les capacités de ce prototype. Ce ne sont pas les limites globales du
système. Les agents doivent consulter `capabilities()`, pas déduire les
budgets depuis le stockage interne.

L'apprenant temporel reçoit déjà les observations dans l'ordre et
produit les mêmes messages de prédiction via `TemporalAdapter`. Le futur coordinateur
pourra remplacer la limite d'un flux par des continuations explicites ;
cette évolution devra être versionnée et testée, plutôt que simulée en
mélangeant des épisodes dans le modèle actuel.

## Vérification reproductible

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.integration_probe --out integration.json
~~~

La sonde compare les prédictions et l'état neuronal à ceux de l'apprenant
direct sur les mêmes événements et résultats. Deux agents simulés
contribuent au même contexte. Une reprise JSON se produit avec une action
déjà réalisée et un résultat encore en attente ; la livraison répétée du
résultat ne provoque pas d'apprentissage supplémentaire.
