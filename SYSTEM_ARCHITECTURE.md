# Architecture commune et frontières des pièces

Les interfaces sont définies avant d'étendre l'apprenant. Elles empêchent
les futurs agents de dépendre des numéros de tâches, du masque de présence,
des coordonnées S² ou des deux actions du laboratoire. Elles ne garantissent
pas l'absence de toute évolution de l'architecture.

La [version partagée](FIRST_PIECE_SCALE.md) conserve les mêmes contrats.
Elle ajoute des symboles opaques et des listes d’actions configurables ;
sa mémoire et ses règles de routage restent des détails privés de l’apprenant.

## Responsabilités

| Pièce | Responsabilité | État |
|---|---|---|
| Contrats communs, `setharkk/contracts.py` | Messages JSON versionnés, identités, ordre logique, unités | Implémentés, version 1 |
| Adaptateurs, `FirstPieceAdapter`, `TemporalAdapter`, `SharedAdapter`, `RenewableAdapter`, `ConsolidatedAdapter` et `CalibratedAdapter`, `PlasticRevisionAdapter` | Traduire les mêmes messages vers l'apprenant choisi ; conserver sa frontière de reprise | Implémentés, un flux et une action en attente |
| Première pièce neuronale | Mémoire d'événements, prédictions et modification des prototypes S² | Présence, ordres et combinaisons bornées ; version partagée entre contextes |
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
Les transactions utilisent une copie temporaire adaptée à l'opération.
Dans la famille partagée, une observation possède l'épisode, les nouvelles
liaisons et le RNG ; elle lit les banques. Un retour possède les banques,
les données du contexte concerné et le journal de validation actif.
Les références de présence et temporelle conservent une copie complète.
Les [mesures](PRIORITY_FIXES.md) publient le coût et les limites de ces copies.

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

## Capacités de la première pièce partagée

`SharedAdapter` annonce `stream.symbol` et `stream.end`, un vocabulaire
opaque borné, deux à seize actions et au plus trente-deux contextes. La
requête choisit toujours un candidat effectivement prédit ; les arguments
restent vides et la mesure est encore `lab.success/binary`.

La banque S² est commune à tous les contextes. Ceux-ci possèdent des
tampons d’observations et des statistiques d’erreur, sans réseau privé.
La recherche peut inclure une égalité de contexte dans une combinaison
observée, sous un budget global. Une validation prospective protège
l’admission ; son périmètre est fixé avant les données utilisées pour décider.

L’identité de reprise est `first_piece.shared-compositions-s2.v1`.
Les bitsets de présence et d’ordre sont des chaînes hexadécimales, pas des
entiers JSON dépassant 2^53−1. Les références historiques restent restaurables
par leurs propres adaptateurs ; aucune conversion implicite n’est annoncée.

La copie transactionnelle spécialisée isole les banques, le RNG, les
listes de mémoire, l’épisode et les résumés mutables. Les anciens enregistrements
sont immuables en interne et partagés en lecture. Les états exposés aux
agents sont des copies détachées. Le verrou et la limite d’une action en
vol restent nécessaires ; le planificateur, l’ingestion de plusieurs flux
et le journal physique durable ne sont pas fournis par cette optimisation.

## Recherche renouvelable, même autorité d'apprentissage

`RenewableAdapter` conserve les contrats version 1 et la frontière d'une action
en attente. Son cœur utilise une identité distincte et le format 3 ; un ancien
état partagé doit suivre un import explicite. Les
[instructions](RENEWABLE_SEARCH.md) précisent le risque historique conservé.

Les agents peuvent lire les capacités du mode et les métriques de bloc, risque,
compteurs à vie et mémoire. Ils ne remettent pas le budget à zéro et ne modifient
pas sa taille au milieu d'une reprise. La première pièce déclenche la recherche
automatiquement depuis les retours appris ; le coordinateur futur devra encore
arbitrer le temps CPU et les expériences, et conserver un journal durable.

Les [mesures longues](RENEWABLE_SEARCH_RESULTS.md) montrent les échecs historiques
du mode renouvelable sans mémoire protégée. Le mode consolidé ci-dessous les
corrige dans le protocole testé ; les anciens modes restent disponibles avec
leurs propres limites et identités de reprise.

## Compétence consolidée, même interface

`ConsolidatedAdapter` conserve les contrats version 1, une seule autorité
d'apprentissage et une action en attente. Son identité est
`first_piece.consolidated-compositions-s2.v1`, avec un checkpoint de format 4.
Les [instructions](CONSOLIDATION.md) définissent les imports explicites depuis
les formats antérieurs, y compris la préservation des requêtes, du risque
déjà dépensé et des validations en cours.

Après une admission, une copie des prototypes S² sert les prédictions
structurées. Elle ne reçoit plus de gradients et n'est remplacée qu'après
une nouvelle admission. Les banques plastiques continuent leurs mises à jour.
Dans les modes consolidé et calibré de formats 4 et 5, les candidats sont
ajustés depuis les buffers récents ; leurs poids plastiques n'initialisent
pas les candidats. La révision de format 6 ci-dessous ajoute ce transfert.
Il existe une seule compétence protégée commune, sans réseau privé par agent.

Les nouvelles validations fixent cinq horizons et la référence servie avant
leurs données prospectives. Pour un remplacement ciblé, la borne de
préservation utilise une amplitude calculée sur toutes les routes possibles
hors du contexte ciblé. Les détails et hypothèses sont dans le
[protocole](CONSOLIDATION_PROTOCOL.md). Un import conserve les trois horizons
d'une ancienne validation jusqu'à sa clôture ; les cinq horizons s'appliquent
aux nouvelles tentatives.

Les [mesures](CONSOLIDATION_RESULTS.md) publient la rétention et les changements
corrigés, ainsi que la surconfiance sous bruit, un délai d'admission accru et
les coûts supplémentaires. Le coordinateur devra consulter les capacités
et métriques plutôt que supposer les budgets des anciens modes. Les objectifs,
le dialogue, les agents autonomes et l'exécution physique restent à construire.

## Probabilité servie et compétence validée

`CalibratedAdapter` conserve les contrats et la frontière d'une seule action
en attente. Son identité est `first_piece.calibrated-compositions-s2.v1`,
avec un cœur de format 5. Les [instructions](CALIBRATION.md) définissent
les imports explicites et la conservation d'une prévision déjà annoncée
jusqu'à son reçu ou sa clôture.

Le modèle distingue la lecture brute de la compétence et la probabilité
calibrée servie. La première gouverne les déclencheurs et comparaisons
d'admission : une mauvaise règle continue à provoquer une recherche même
si la calibration réduit sa surconfiance. Le risque statistique d'admission
s'applique à cette compétence, sans garantir le calibrateur adaptatif.

La seconde utilise les derniers résultats des actions exécutées par contexte.
L'adaptateur publie cette probabilité dans la prévision Bernoulli ; `learn`
retourne la probabilité annoncée avant l'observation du résultat. Les modèles
historiques conservent leur lecture brute. La calibration ne fournit pas une
incertitude épistémique ni une valeur d'objectif.

Le calibrateur conserve un cache borné des probabilités et quatre sommes.
Les copies transactionnelles l'isolent, et les reprises le vérifient contre
la banque protégée et les épisodes retenus. Une admission reprojette les
lignes récentes sur la nouvelle compétence. Ces calculs sont distincts
des mises à jour neuronales et ne créent pas de réseau privé par agent.

Le [rapport](CALIBRATION_RESULTS.md) publie calibration, conservation, délais,
ressources et limites de sélection d'actions. Le coordinateur futur devra
tenir compte de ces limites et des métriques annoncées.

## Poids plastiques et révisions prospectives

`PlasticRevisionAdapter` conserve les contrats, l'autorité unique et les
prévisions déjà annoncées lors d'un import. Son cœur de format 8 réutilise
les prototypes plastiques par un regroupement des routes sur S², avec un
test sur les labels de fit et un redémarrage de l'âge d'optimisation.
Les [instructions](PLASTIC_REVISION.md) décrivent les imports explicites.
Un raffinement prospectif du même programme permet aussi d'utiliser les
poids plastiques devenus plus précis lorsque le déclencheur d'erreur
structurelle reste inactif. Ses labels de préparation ne servent pas de
preuve d'admission.

Le candidat et la banque de contrôle gardent le budget de gradients par fit.
La pertinence d'une nouvelle structure est comparée à un taux de base par
contexte, fixé depuis les données de fit avant validation. Une différence
de taux de bruit entre contextes suffit ainsi moins facilement à remplacer
une compétence d'action. Cette fréquence est un contrôle statistique,
pas une banque neuronale privée.
La validation utilise les amplitudes de gains connues avant chaque label,
une référence figée et sept horizons déclarés. Quatre réglages exponentiels
partagent le risque ; la borne de conservation du complément utilise aussi ces amplitudes
et reste uniforme dans le temps. Un ancien essai importé garde sa politique jusqu'à sa clôture.

Un examen des données récentes peut clore un candidat
dépassé à deux horizons déclarés. Cette clôture n'est pas une admission et
ne rend aucun risque au système. Les prochains essais restent prospectifs.
Le coordinateur devra lire ces métriques et leur coût de recherche,
sans utiliser une clôture comme preuve de compétence.

Le [protocole](PLASTIC_REVISION_PROTOCOL.md) et le
[rapport](PLASTIC_REVISION_RESULTS.md) donnent les unités, les comparaisons
et les limites. La révision fournit une première pièce d'apprentissage,
pas les objectifs, le dialogue ou les agents exécutant des tâches du PC.

## Publication d'un retour pendant un calcul long

Une condition sérialise les traitements de reçus. L'adaptateur prépare une
copie isolée sous verrou, calcule son apprentissage hors du verrou, puis
publie ensemble le modèle, la révision et l'accusé. Un échec préalable
ne consomme pas la requête. Un doublon concurrent attend cette publication
et retrouve le même accusé sans autre gradient.

Pendant ce calcul, les lecteurs voient l'état cohérent précédent, y compris
la requête en attente. Cette reprise peut recalculer un retour dont l'accusé
n'était pas publié ; elle ne garantit toujours pas l'unicité d'une action
physique. Le coordinateur devra ajouter un journal durable et des budgets
de calcul. Un seul flux et une seule action restent en vol ; une écriture
concurrente ne peut pas mélanger deux épisodes.

Le format neuronal 8 n'est pas une nouvelle version des messages JSON.
L'import explicite depuis les formats plastiques 6/7 conserve les identités
de la prédiction et de la requête déjà annoncées. Les métriques résumées
`metrics(detailed=False)` permettent aux futurs agents de lire les compteurs
sans recopier le journal détaillé.


## Service de calcul coopératif

Le [contrat de première pièce](FIRST_PIECE_COOPERATIVE.md) fournit une
continuation versionnée `first_piece.cooperative.v1` :
`begin_receipt`, `advance(max_units)`, `work_status`,
`coverage`, `checkpoint` et `restore`.
Le cortex est responsable de l'ordonnancement des quotas, de la persistance
atomique du checkpoint complet et du journal des effets de l'exécuteur.
Il n'envoie pas une nouvelle action tant que la précédente reste en attente.

Une erreur dans le calcul reconstitue le travail privé depuis l'état servi,
en conservant le reçu de l'exécution. La reprise ne demande pas une nouvelle
action à l'exécuteur.

Le service publie le modèle seulement après calcul complet. Une pause
conserve la prévision et la révision précédentes. La couverture annonce
des nombres d'observations récentes par action et route ; elle ne remplace
pas une mesure d'incertitude. Le quota n'est pas un délai garanti.

Le checkpoint du service contient celui de l'adaptateur actif format 8
et une continuation scellée contre les altérations accidentelles.
Il ne permet pas de fusionner des copies concurrentes du cœur, ni de
reconstruire des effets PC absents du journal d'exécution.

Le module expérimental `AdaptiveTraceLearner` possède son propre
checkpoint et ses propres capacités (deux actions, huit contextes).
Il n'est pas un remplacement compatible du service courant.
Un futur branchement exigera la validation de son adaptateur, de sa
continuation de calcul et des tâches déjà couvertes par le moteur actif.


## Branchement optionnel du moteur de trace v2

AdaptiveTraceService expose les mêmes opérations publiques que CooperativeService :
observation, prévision, réservation d'action, reçu, quota, couverture et checkpoint.
La classe de base sélectionne l'adaptateur, la continuation et leur protocole par
des points d'extension ; ses valeurs par défaut conservent le service format 8.

Le [backend de trace v2](FIRST_PIECE_TRACE_V2.md) annonce deux actions binaires,
huit contextes, 64 symboles et son propre format neuronal 2. Son identifiant permet
au coordinateur de reconnaître une représentation différente plutôt que de charger
un checkpoint d'un autre moteur. Les poids sont figés pendant les essais futurs ;
la calibration et l'historique causal sont persistés avec le reste du modèle.

La partition géodésique et le replay sont reprenables. Le modèle servi reste
cohérent jusqu'à publication du reçu complet. Le cortex peut donc allouer un quota
et persister un service en cours, en gardant le journal d'exécution externe.
Ce branchement ne démontre pas la couverture des tâches propres au format 8,
et n'ajoute pas de dialogue, d'objectifs autonomes ou d'exécution PC.


## Catalogue configurable du moteur de trace

[ActionTraceService](ACTION_CATALOGUE.md) ajoute le backend explicite
first_piece.action-trace-s2.v3, format neuronal 3, continuation
first_piece.action-cooperative.v3. Chaque action annoncée a une sortie S² ;
les contrats, les identités des candidats et la mesure Bernoulli sont conservés.

Le coordinateur lit action_count, point_budget, record_budget,
validation_horizons et les autres capacités avant de fixer ses expériences.
La couverture est indexée sur tout le catalogue et sur les résultats réels.
La taille du catalogue est contrôlée avant allocation par des réserves
de ressources, sans plafond constant de seize.

Les copies de retour possèdent les champs mutables concernés et partagent
les lignes passées immuables. Les continuations de partition et de replay
restent reprenables par quota. Un import v2 est explicite et conserve les
identités en attente ; l'essai importé garde sa politique jusqu'à clôture.

Le catalogue demeure fixe. Les actions à arguments, leur génération dynamique,
les continuations de plusieurs flux, la sélection d'expériences et le journal
des effets physiques restent des responsabilités à construire.
