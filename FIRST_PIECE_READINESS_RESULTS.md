# Première pièce : reprise du calcul et représentation des répétitions

Le service coopératif conserve exactement le moteur plastique de format 8
dans les essais de parité. Il suspend recherche et replay par quotas, conserve
la prévision servie jusqu'à publication et expose les observations récentes
par action. Le prototype de représentation apprend la séparation AAB/ABB
dans l'expérience prévue, mais ses probabilités deviennent trop confiantes
sous bruit. Il reste un module expérimental distinct du moteur servi.

Protocole fixé avant mesures : [FIRST_PIECE_READINESS_PROTOCOL.md](FIRST_PIECE_READINESS_PROTOCOL.md).
Base du moteur : `9dbc2876d8347667dd46deddd9f340be96640c4d`.
Code publié : `8d00725df14a121a3ca39a622e3b87462c13e6ed`.
Le [contrat d'intégration](FIRST_PIECE_COOPERATIVE.md) décrit les responsabilités
du coordinateur, les checkpoints et les garanties effectivement fournies.

## Vérification et provenance

Les tests couvrent recherche exacte, reprise JSON à toutes les phases,
permutations et curseurs de replay, changement de passe, validation prospective,
erreur tardive de publication, déduplication, couverture des actions manquantes
erreur interne après mutation d'un état privé,
et passage d'un adaptateur appris vers le service avec action en attente.
La suite compte **163 tests**, contre 153 sur la base.

Un test supplémentaire reproduit un défaut du premier commit de service
`feef8fb8216cdae67fd6e902af53ba4c00345363` : une exception après
la mutation du feedback laissait phase feedback/étape privée 1, contre étape
servie 0, et empêchait la restauration du checkpoint.
La correction reconstruit le travail privé en gardant le reçu. Un nouvel essai
apprend une seule fois ; l'action exécutée n'est pas demandée de nouveau.
La [preuve avant/après](readiness_results/recovery_review.json) conserve le défaut
reproduit sous les deux systèmes et les dix tests ciblés du candidat corrigé.

Les candidats sont d'abord appliqués dans un checkout jetable de CI.
Les SHA Git des trois fichiers appliqués sont comparés aux blobs publiés :
[source_proof.json](readiness_results/source_proof.json).
L'archive de préparation est dans l'historique Git et n'est plus un fichier
actif du dépôt. La CI publiée exécute directement les fichiers du commit.

Les résultats intégraux, y compris les journaux d'admission et les mesures
probabilistes défavorables, sont conservés dans
[linux.json](readiness_results/linux.json) et
[windows.json](readiness_results/windows.json).
La [comparaison](readiness_results/comparison.json) distingue les différences
numériques tolérées des durées et tailles de sérialisation.
Les [états de CI](readiness_results/workflow_status.json) identifient les
runs du commit publié.

Python 3.11, bibliothèque standard uniquement, CPU des runners GitHub.
Ces mesures ne constituent pas un profil de la carte RTX ou du PC de l'utilisateur.

## Calcul coopératif

Sur **32 000 retours**, **64 symboles** et **16 contextes**, les prévisions
correspondent exactement au moteur direct dans chaque exécution.
Les checkpoints complets sont comparés tous les 4 000 retours, puis à la fin,
après neutralisation des durées de recherche. Programmes, poids, RNG,
calibration, journaux et compteurs restent identiques.

Le parcours comporte 38 tentatives, deux admissions et **1 197 512 gradients**
dans chaque moteur. Le service consomme **1 411 193 unités** en **42 757 appels**
de quota 128. Il reprend de vrais travaux de structure, refresh de recherche
et examen de raffinement. Un doublon final ne modifie pas l'état.

Le fit forcé de charge maximale testée utilise **4 096 lignes**,
quatre passes et deux banques, soit **32 768 gradients**.
Les modes structure et renforcement des poids existants sont comparés au
moteur synchrone. Le test forcé mesure le coût d'un fit ; il ne prétend pas
qu'une admission a lieu à cet instant du parcours naturel.

| Mesure initiale du protocole | Linux | Windows |
|---|---:|---:|
| Fit structure synchrone | 885 ms | 834 ms |
| Pic d'un appel coopératif structure | 22,5 ms | 19,8 ms |
| Nombre d'appels structure, quota 128 | 306 | 306 |
| Fit renforcement synchrone | 663 ms | 626 ms |
| Pic d'un appel coopératif renforcement | 19,9 ms | 18,8 ms |
| Nombre d'appels renforcement, quota 128 | 257 | 257 |

Ces valeurs sont celles de la première mesure gelée, avant ajout de diagnostics
probabilistes. Les nouvelles mesures brutes donnent leurs propres durées.
Le travail total conserve son coût ; la réduction concerne la durée entre
deux possibilités de rendre la main. Le quota ne garantit pas un délai dur :
initialisation géodésique, tri, calibration, mélange, publication, sérialisation
et restauration conservent des phases atomiques dépendant des budgets.

Le service garde un état servi et un état privé pendant le calcul.
Des banques de fit et des bitsets de recherche s'ajoutent temporairement.
Les compteurs de paramètres du moteur décrivent ce moteur, pas le pic mémoire
Python de toutes ces copies. Aucun pic RSS du service n'a été mesuré.
Le partage des lignes de contextes inchangés évite leur copie systématique ;
les banques et la continuation ont malgré cela un coût supplémentaire.

## Couverture par action

`coverage(prediction_id)` examine les lignes réellement étiquetées
retenues dans les buffers, pour la route de la prévision courante.
Elle publie le nombre observé et positif, puis un statut selon un seuil
configurable de 1 à 1 024, égal à 32 par défaut.
Les passes de replay et les redélivrances de reçu ne créent pas d'observation.

Une route commune peut agréger plusieurs contextes : c'est le périmètre
de partage du programme servi. Une action absente est explicitement
non observée. Une action ayant assez de lignes n'est pas pour autant
certifiée sur de nouvelles situations. L'intervalle épistémique reste absent.

## Représentation adaptative sur S²

Le protocole apparie les deux classes avec le même contexte et le même préfixe.
Le premier ordre, la présence et la longueur restent identiques.
La cible ne rentre jamais dans les apprenants. Les actions 0/1 et leurs résultats
sont identiques dans les trois variantes.

L'état récurrent est un point S² :

`h(t+1)=Exp_h(t)(0.75 Log_h(t)(e(symbole)))`.

Les codes fixes sont issus d'un hash sans résultat cible. Le coefficient,
l'encodeur et l'opérateur de séparation binaire sont fournis.
Les centres viennent du clustering géodésique des observations ;
les sorties sont des prototypes S² ajustés par gradients tangents.
Une séparation doit battre prospectivement la référence et un contrôle
de même capacité avant d'être publiée. Le risque annoncé est sommable à vie ;
il porte sur ces gains bornés, pas sur l'invention d'une représentation universelle.

Par graine : 2 048 retours indépendants, 16 384 structurés, 8 192 indépendants
et 4 096 de récupération. **30 720 épisodes**, trois graines, soit
**92 160 épisodes par variante et par système**.
Windows reproduit les mêmes trois expériences ; il n'ajoute pas trois
graines indépendantes. Chaque sonde sans apprentissage comporte 512 épisodes.

| Exposition au signal | Adaptatif, graines 0 / 1 / 2 | Encodeur sans séparation | Format 8, graines 0 / 1 / 2 |
|---|---|---|---|
| 512 | 50 % / 50 % / 50 % | 50 % | 47,85 % / 50,59 % / 48,24 % |
| 2 048 | 50 % / 50 % / 50 % | 50 % | 51,17 % / 50,39 % / 48,63 % |
| 8 192 | 100 % / 100 % / 100 % | 50 % | 47,07 % / 56,45 % / 51,17 % |
| 16 384 | 100 % / 100 % / 100 % | 50 % | 50,20 % / 48,83 % / 50,98 % |

L'admission a lieu après **2 432 / 3 584 / 2 432 épisodes de signal**,
soit aux étapes totales 4 480 / 5 632 / 4 480.
Conclure à l'échec au deuxième horizon aurait manqué l'admission ultérieure.

À la fin du signal, après bruit et après récupération, la compétence adaptative
reste à **100 %** dans les sondes ordinaires, avec préfixes plus longs
(9..12 distracteurs contre 2..7 en apprentissage) et dans un contexte neuf.
Aucune séparation n'est admise pendant les deux phases de bruit.
La reprise JSON d'une prévision et d'une validation figée est exacte.

L'expérience conserve deux feuilles après une admission.
Le maximum relevé aux sondes de ressources est **36 points S² de modèle**
avec banques temporaires et centres, et **512 épisodes retenus**.
En fin de parcours, 22 points sont alloués. Les codes d'observation fixes,
les ancres, le point récurrent et les statistiques sont distincts de ce compte.
Les plafonds configurés restent huit feuilles, profondeur quatre et
256 lignes par feuille. Ces maxima configurés n'ont pas tous été saturés.

## Résultat défavorable : probabilités sous bruit

La conservation de la compétence est mesurée sur des sondes structurées.
Elle ne signifie pas que les observations bruitées sont bien prédites.
Le Brier ci-dessous utilise la probabilité **avant** apprentissage,
l'action exécutée et son résultat réellement observé. Une valeur plus basse
est meilleure ; une prévision constante 0,5 obtient 0,25 sur le bruit équilibré.

| Interruption bruitée, graine | Adaptatif | Encodeur sans séparation | Format 8 |
|---|---:|---:|---:|
| 0 | 0,4897 | 0,2531 | 0,2588 |
| 1 | 0,5030 | 0,2533 | 0,2596 |
| 2 | 0,4907 | 0,2540 | 0,2584 |

La banque protégée conserve la règle et reste confiante malgré des résultats
devenus indépendants. Le prototype n'a pas la lecture calibrée du moteur actif.
Ce défaut doit être corrigé et testé avant toute promotion du prototype :
les critères de compétence prévus passent, la qualité probabiliste régresse.

## Limites restant avant une extension du rôle

- Le moteur servi conserve sa grammaire de présence/premier ordre/contextes
  et ses plafonds de symboles, routes, lignes et capacité de recherche.
  Le nouveau service l'ordonnance ; il n'en change pas la représentation.
- Le prototype traite deux actions et huit contextes au maximum, sous
  frontières d'épisode fournies. Le vocabulaire est limité à 64 codes.
  Il n'est pas intégré à l'adaptateur actif ni au travail coopératif.
- Les centres et la récurrence sont sur S², mais l'encodeur et l'opérateur
  binaire sont définis par le concepteur. Le mécanisme n'invente ni opérateurs,
  ni objectifs, ni une géométrie nouvelle.
- Les propositions du prototype comportent encore un clustering et un replay
  synchrones. Les pics mesurés de `learn` sont dans les JSON ;
  sa propre continuation par quota reste à construire.
- Le prototype n'a pas de mécanisme distinct de révision des poids protégés
  sans séparation supplémentaire, ni de fusion ou suppression de feuilles.
  Le remplacement de règles et les changements successifs ne sont pas
  validés pour ce module.
- La pertinence du mécanisme au-delà de deux familles de séquences,
  pour des observations de fichiers/applications, n'est pas établie.
  Un contrôle géométrique euclidien et une baseline récurrente fixe disposant
  déjà d'une lecture conditionnée par l'état seraient nécessaires pour
  attribuer un bénéfice propre à S² ou à la croissance des états.
- Le coordinateur d'agents, les objectifs autonomes, le dialogue,
  l'exécuteur PC, la persistance système et plusieurs transitions en vol
  restent à construire.

Le service fournit un contrat utilisable par un futur coordinateur.
La promotion du prototype exige ses propres adaptateur, continuation,
calibration et essais de remplacement/rétention sur les tâches déjà couvertes.
Ce rapport démontre une capacité synthétique supplémentaire et une amélioration
de l'ordonnancement ; il ne démontre ni un paradigme inédit ni un world model général.
