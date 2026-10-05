# Corrections prioritaires du format 7

Le format 8 corrige les quatre défauts reproduits par la
[revue](CODE_REVIEW_PLASTIC.md) et réduit les coûts de copie et de recherche.
Le réseau conserve ses prototypes sur S², sa lecture géodésique, ses
gradients tangents et ses applications exponentielles. Aucune banque
euclidienne apprise n'est ajoutée.

## Défauts corrigés

| Priorité | Défaut reproduit | Correction | Vérification |
|---|---|---|---|
| P1 | Un retour calculé sur une copie modifiait le journal de validation du parent | Copie profonde du journal actif, sans recopier les archives immuables | Frontière réelle 639 retours / 127 labels de validation ; échec injecté après apprentissage et avant publication ; checkpoint parent restaurable et reçu rejouable |
| P1 | La moyenne de points sources valides pouvait atteindre le lieu de coupure d'une ancre | Vérifier le domaine de `learnable_point` avant transfert ; repli neutre | Sources [-1,0,±0.1] normalisées ; replay et restauration du candidat possibles |
| P2 | Le plafond de délai s'appliquait au premier succès, alors que le protocole demandait sa confirmation | Vérifier `confirmation_global_labels` | Première réussite à 12000, confirmation à 13000 : critère refusé |
| P3 | Les références de présence et temporelle acceptaient des compteurs neuronaux incohérents | Équations propres aux retours, fits, labels décisifs et admissions de chaque moteur | Totaux et compteurs actifs falsifiés refusés ; états valides et reprises historiques conservés |

Le contrôle d'un checkpoint vérifie des invariants, pas une preuve
cryptographique de son histoire. Les équations des références sont
différentes : la présence omet son gradient en ligne sur le label qui
clôture une validation ; le moteur temporel met à jour ses deux banques
avant une éventuelle admission.

## Optimisations appliquées

| Coût identifié | Changement | Frontière conservée |
|---|---|---|
| Copie du calibrateur et des banques à chaque symbole | Copie d'observation possédant épisode, RNG, vocabulaire, liaisons et table de calibration ; banques lues | Les retours possèdent leurs banques et les données modifiables ; une copie générale sans contexte reste isolée |
| Construction bit par bit de l'index dans les épisodes denses | Transposition exacte par blocs de huit lignes ; chemin creux conservé | Tests indépendants des masques, y compris blocs partiels ; même programme retenu |
| Verrou des lecteurs tenu pendant recherche et replay | Calcul de la copie hors verrou ; condition sérialisant les reçus | Lectures de l'état précédent cohérent ; doublons concurrents n'apprennent qu'une fois ; API synchrone |
| Recherche alternative ignorée dans le mode de confiance | Fit du programme protégé directement, avec zéro recherche alternative dans le journal | Conditions de proposition, gradients, validation et risque conservés |
| Allocation de nouvelles listes bornées et lectures géodésiques répétées | Append puis éviction de tête ; cache borné par prototype dépendant des points, ancres et température | Ordre des enregistrements conservé ; valeurs exactes ; aucun paramètre appris supplémentaire |
| Copie des journaux pour toute lecture de métriques | `metrics(detailed=False)` omet seulement `searches` et `decisions` | Détail par défaut et checkpoint complet |
| Reconstruction répétée de tous les couples légaux à la reprise | Inverse de l'index triangulaire par recherche binaire | Couples non liés au vocabulaire refusés |

L'éviction en tête d'une liste reste linéaire dans sa longueur bornée :
elle évite une allocation complète, mais ne crée pas une file à coût
constant. Le cache de lecture est dérivé et non sérialisé. Les copies
spécialisées sont une propriété interne contrôlée par l'adaptateur ;
un appel privé avec un contexte arbitraire n'est pas une nouvelle API publique.

## Compatibilité et cohérence avec les prochaines pièces

Identité `first_piece.plastic-revision-s2.v3`, checkpoint neuronal 8.
Les messages du système restent version 1. L'import des formats 6/7 est
explicite, pour le cœur et pour l'adaptateur :
`from_plastic_revision_checkpoint`. Il conserve les essais en cours,
leurs banques, horizons, risques, prévisions et requêtes. Les anciens
journaux de confiance gardent leur travail historique ; les nouveaux
comptent zéro recherche alternative.

Le coordinateur futur lit les métriques et prévisions versionnées.
Il possède toujours un seul flux et une action en attente. Pendant un fit,
les lecteurs consultent la révision précédant la publication ; les reçus
concurrents attendent, puis retrouvent le résultat publié. L'adaptateur
n'écrit pas automatiquement un journal durable et ne garantit pas
l'unicité d'une action physique après une panne.

## Preuves et mesures

**153 tests réussis sous Windows et Linux**, dont 14 nouvelles régressions.
Les quatre défauts sont refusés ou évités sur les deux systèmes. La
continuation de 32000 retours donne un écart maximal de prévision de zéro,
avec le même état prédictif et un import réel de format 7 en validation.

- [Validation du candidat exact sur les deux systèmes](https://github.com/Setharkk/Remake-setharkk/actions/runs/37274175341).
- [Résultats Linux](priority_fix_results/linux.json), [Windows](priority_fix_results/windows.json)
  et [comparaison / identifiants des sources](priority_fix_results/comparison.json).

Le candidat est appliqué seulement dans l'espace CI jetable pour cette
prévalidation. Les identifiants Git de ses 14 fichiers sont conservés et
comparés à ceux du moteur publié. Le paquet temporaire n'est plus présent
dans l'arbre courant ; l'historique Git permet de le reproduire.

| Mesure, médiane | Linux avant | Linux après | Windows avant | Windows après |
|---|---:|---:|---:|---:|
| Adaptateur, ms/épisode, 96 épisodes × 3 répétitions | 13.771 | 0.778 | 8.368 | 0.458 |
| Recherche dense, ms, 512 lignes × 5 répétitions | 299.34 | 108.91 | 216.12 | 76.80 |
| Fit complet, secondes, 4096 lignes × 3 répétitions | 0.773 | 0.801 | 0.514 | 0.529 |

L'adaptateur gagne **17.71× sur Linux et
18.27× sur Windows**. La recherche
dense gagne **2.75× et 2.81×**,
avec le même programme. Ces ratios concernent les cas décrits, sans garantir
le même gain sur le PC de l'utilisateur.

Le fit complet reste légèrement plus lent dans ces petites mesures
(0,801 contre 0,773 seconde sur Linux ; 0,529 contre 0,514 sur Windows).
Les contrôles de transfert et le cache n'en suppriment pas les 32768
gradients. Libérer le verrou corrige l'accès des lecteurs, sans accélérer
tous les calculs ni rendre les retours instantanés.

La publication du moteur déclenche également les cinq cas de délai et les
30 cas indépendants Windows/Linux du protocole complet. Leurs résultats
seront consignés après la fin des exécutions.

Les benchmarks comparent la référence Git
`3bc75f676b3b93244e099f10db948d1a6be71f85` et le code corrigé, sans profileur,
sur les mêmes flux. L'ordre avant/après alterne. Les coûts sont mesurés
sur CPU GitHub Actions, pas sur la RTX de l'utilisateur.

La comparaison de continuation contrôle 32000 retours à 64 symboles et
16 contextes. Elle neutralise seulement format, identité, durée et
les trois compteurs de recherche alternative retirée dans les raffinements.
Les poids, prévisions, programmes, décisions, états aléatoires et compteurs
de gradients restent comparés. Les mesures de fil d'observations
comparent aussi le modèle direct et l'adaptateur.

## Limites restantes

Ces corrections ne rendent pas la première pièce générale. Les programmes
gardent trois prédicats au maximum et huit routes ; présence, premier ordre
et égalité de contexte forment encore une bibliothèque fournie. Le support
de fit et de validation porte sur les routes, sans garantir une couverture
de chaque couple action-route. Les expériences utilisent une exploration
uniforme extérieure au modèle.

Un fit à 4096 lignes et quatre passes effectue encore 32768 gradients
pour ses deux banques, sans suspension ni quota par tick. Le reçu qui le
déclenche attend ce calcul. Libérer le verrou permet les lectures, mais
ne garantit pas un temps de réponse sous le GIL Python. Le coordinateur
devra budgéter ou découper ces calculs avant une boucle PC exigeant une
latence bornée.

Les tampons, archives et calibrations restent bornés. La recherche
symbolique, les critères statistiques et ces données constituent une
part importante de la capacité et du coût. Les tests ne démontrent pas
une supériorité de S² sur un réseau euclidien ni une innovation scientifique.

Objectifs autonomes, choix appris des expériences, dialogue, essaim
coordonné, continuations parallèles et exécution sur les applications
du PC restent à construire.
