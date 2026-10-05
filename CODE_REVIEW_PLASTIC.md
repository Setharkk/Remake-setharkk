# Revue complète de la première pièce — 5 octobre 2026

Cette revue conserve les défauts du moteur audité de format 7. Les corrections,
optimisations et preuves du format 8 figurent dans [PRIORITY_FIXES.md](PRIORITY_FIXES.md).

Le moteur conserve une géométrie neuronale sur S² et réussit ses 139 tests
existants sous Windows et Linux. La revue révèle néanmoins **deux défauts P1
dans le moteur plastique**, **un défaut P2 du critère de délai** et **un défaut
P3 des reprises historiques**. Les copies de l'adaptateur sont le principal
coût évitable mesuré sur le chemin ordinaire. Les tâches denses ajoutent
un coût de construction des relations qui dépasse celui du classement
des hypothèses.

Cette livraison contient les sondes, les profils et ce rapport. Le moteur
audité n'a pas été corrigé dans cette livraison.

## Périmètre et méthode

Commit audité : `f6a1ea4f74ac546bed79eef562894320c358790e`. Moteur plastique de format 7,
identité `first_piece.plastic-revision-s2.v2`. Les ajouts de revue ne modifient
aucun fichier de `first_piece/`, de `setharkk/` ou du protocole mesuré.

L'[inventaire](plastic_revision_review_results/source_inventory.json) couvre
85 fichiers : 34 fichiers du paquet et des contrats, 12 fichiers de tests,
9 outils de validation, 13 workflows et 17 documents de spécification ou
de résultats. Les 31 modules Python du paquet et des contrats représentent
5 595 lignes. Les anciens laboratoires `cortex_lab_v0/` et
`cortex_lab_v1/` sont des références archivées hors du périmètre de cette
revue de la première pièce.

L'examen suit les appels de réception, prévision, apprentissage, recherche,
admission, copie transactionnelle, calibration, sauvegarde et imports.
Il compare les invariants au code de restauration et les critères des
benchmarks à leurs protocoles. Les scripts historiques de mesure sont
examinés pour leur raccord au moteur, pas réexécutés sur des millions
d'interactions : leurs résultats publiés constituent l'historique.

Les nouvelles sondes utilisent des données déterministes, un défaut injecté
après l'apprentissage d'une copie et des profils CPU. Elles publient les
défauts observés ; un job de revue vert signifie que les sondes et la suite
ont abouti, pas que tous les constats sont corrigés.

- [Sonde reproductible](validation/plastic_revision_review.py).
- [Exécution finale Windows et Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37270906361).
- [Données Linux](plastic_revision_review_results/linux.json).
- [Données Windows](plastic_revision_review_results/windows.json).
- [Comparaison des reproductions](plastic_revision_review_results/comparison.json).

## Défauts de fonctionnement

### B1 — P1 : la copie transactionnelle partage un journal encore mutable

Emplacements :
[shared.py, lignes 171–193](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/shared.py#L171),
[plastic_revision.py, lignes 274–288](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/plastic_revision.py#L274),
[plastic_revision.py, lignes 312–329](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/plastic_revision.py#L312)
et [adapter.py, lignes 201–213](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/adapter.py#L201).

`_transaction_copy()` fait une nouvelle liste `searches`, mais conserve les
mêmes dictionnaires internes. Le commentaire dit qu'ils sont immuables.
La révision plastique écrit pourtant dans
`validation.variance_checks` à chaque regard et dans
`validation.refresh_checks` lors des réexamens.

**Reproduction réelle :** après 639 retours, un essai est à n=127.
Une copie reçoit son retour suivant et inscrit le regard 128. Sans publier
la copie, le modèle source reste à 639 retours mais contient déjà les
entrées de variance du regard 128. Il ne peut plus être restauré :
`Variance records and completed looks differ`.

La sonde de l'adaptateur injecte une exception au contrôle final de
`model_revision`, après `candidate.learn()`. La requête et la révision
restent en attente, mais le checkpoint a changé et sa restauration échoue.
L'injection vérifie la garantie de rollback ; elle ne prétend pas que
cette exception survient dans chaque usage normal. La corruption du
modèle source par une copie non publiée est également démontrée sans
injection d'exception.

**Correction attendue :** donner à la copie une propriété exclusive du
journal de l'essai vivant, y compris ses tables et ses listes imbriquées.
Les archives réellement immuables peuvent rester partagées. Vérifier
l'absence de mutation du parent aux regards 128, 512 et 1 024, pendant un
réexamen et après un reçu qui échoue tardivement. Ce défaut doit être
corrigé avant d'optimiser davantage les copies.

### B2 — P1 : une moyenne transférée peut sortir du domaine de l'optimiseur

Emplacements :
[plastic_revision.py, lignes 124–140](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/plastic_revision.py#L124)
et [spherical.py, lignes 38–59 et 100–107](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/spherical.py#L38).

Le repli neutre traite un logarithme indéfini **entre les prototypes
sources**. Il ne vérifie pas que la moyenne obtenue permet encore les
logarithmes vers les ancres du réseau.

**Reproduction :** les points normalisés
`[-1, 0, 0.1]` et `[-1, 0, -0.1]` sont valides pour les deux ancres.
Leur moyenne intrinsèque vaut, à l'arrondi près,
`[-1, 0, 1.39e-17]`, antipode de l'ancre `[1, 0, 0]`.
Le test de gain conserve ce prototype pour des résultats positifs,
avec p≈0,999999628. Le premier gradient de replay échoue avec
`Antipodal logarithm is not unique`. La banque candidate ne passe pas
non plus sa propre restauration. Le compteur `ambiguous_means` reste à zéro.

Il s'agit d'un cas déterministe de domaine numérique ; la revue ne mesure
pas sa fréquence dans les mondes synthétiques déjà publiés.

**Correction attendue :** contrôler la moyenne avec
`learnable_point(value, bank.anchors)` avant de la conserver et employer
le repli neutre déclaré lorsqu'elle n'est pas utilisable. Préserver S²,
les ancres et les applications géodésiques. Tester une moyenne régulière,
des sources antipodales et des sources régulières dont la moyenne tombe
au point singulier d'une ancre.

### B3 — P2 : le délai confirmé du protocole n'est pas celui contrôlé

Emplacement :
[plastic_revision_probe.py, lignes 170–184](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/validation/plastic_revision_probe.py#L170).

Le [protocole](PLASTIC_REVISION_PROTOCOL.md) fixe le pire délai
**confirmé** à au plus 12 000 retours globaux. Le code calcule bien le
premier point réussi et sa confirmation, mais vérifie seulement
`full_competence_global_labels <= 12000`.

**Reproduction :** la sonde exécute les instructions du critère existant
sur une courbe construite qui réussit pour la première fois à 12 000,
puis à 13 000. La confirmation vaut 13 000 et aucune erreur de critère
n'est déclarée.

**Correction attendue :** comparer la confirmation à la limite du
protocole. Conserver les deux unités dans le rapport. Ce défaut
n'invalide pas rétroactivement les trois résultats publiés, dont les
confirmations sont 11 000, 2 000 et 3 000 : ils satisfont aussi la
condition correctement formulée.

### B4 — P3 : les références historiques acceptent des compteurs incohérents

Emplacements :
[learner.py, lignes 230–293](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/learner.py#L230)
et [temporal.py, lignes 286–365](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/temporal.py#L286).

Après un seul retour, ajouter 100 au champ `neural_updates` du checkpoint
de présence ou temporel ne provoque aucun rejet. La référence de présence
annonce ensuite 101 mises à jour ; la référence temporelle en annonce 102.
Les validateurs contrôlent le type et certaines bornes, mais ne relient
pas ce total à l'exposition, aux gradients de fit et aux admissions.

**Portée :** ce défaut concerne les deux références historiques encore
exposées. Le cœur partagé et ses descendants contrôlent déjà cette
équation dans `shared_state.validate_history` ; la sonde ne démontre
aucun contournement équivalent du format 7.

**Correction attendue :** compléter les invariants propres aux références,
sans importer aveuglément les équations d'un autre moteur. Ajouter des
tests de corruption et garder leurs reprises authentiques compatibles.

## Goulots et boucles Python

### O1 — priorité haute : la copie de tout le calibrateur à chaque événement

Les profils portent sur 96 épisodes identiques, huit symboles plus une
surface par épisode, quatre actions, 16 contextes, 4 096 lignes de fit
et 4 096 probabilités en cache. Le modèle source est appris pendant
6 000 retours, possède une banque protégée et ne commence pas un fit
dans ce petit segment. Les états finaux direct et adaptateur sont identiques.

`submit_observation` et `submit_receipt` font chacun une copie. Cela donne
960 copies pour les 96 épisodes. La copie de `CalibratedLearner` utilise
`copy.deepcopy(self._calibration)`, donc recopie le cache de **tous les
contextes**, même pour un symbole qui ne change aucune calibration.

Le chemin adaptateur effectue 4 752 576 appels récursifs à `deepcopy`
et environ 29,46 millions d'appels profilés au total, contre 94 249
sur le chemin direct. Les copies occupent environ 96–97 % du temps
cumulé profilé. Les temps instrumentés servent à localiser le coût ;
la comparaison sans profilage ci-dessous sert à le quantifier.

| Chronométrage sans profilage, médiane de trois répétitions | Linux | Windows |
|---|---:|---:|
| Cœur direct, ms/épisode | 0,089 | 0,157 |
| Adaptateur, ms/épisode | 7,262 | 13,941 |
| Rapport adaptateur/cœur direct | 81,8× | 88,8× |

Ces mesures proviennent de runners CI différents, avec Python 3.11.16
sur Linux et 3.11.9 sur Windows. Elles ne mesurent ni le PC de l'utilisateur,
ni sa RTX, ni un débit garanti en production. Trois répétitions repartent
du même checkpoint ; l'ordre direct/adaptateur est alterné.

**Optimisation proposée :** séparer la transaction d'une observation de
celle d'un retour appris. Une observation symbolique ne devrait pas
recopier les poids ni les caches inchangés. Au retour, cloner les objets
effectivement modifiés : banques plastiques, état d'essai vivant, contexte
touché et son cache. Une admission qui reprojette tous les caches garde
une transaction couvrant tous les contextes. Les références figées peuvent
être partagées en lecture si leur immutabilité est garantie. Tester B1,
la reprise, les reçus répétés et la parité des prévisions avant de retenir
un gain de débit.

### O2 — priorité haute : préparation quadratique des relations denses

`SharedLearner.receive` inscrit l'ordre entre les premières occurrences.
Pour S symboles distincts dans un épisode, le nombre de relations est
S(S−1)/2. La construction des bitsets de recherche rescane ensuite tous
les bits vrais de toutes les lignes, dans `shared.py:289–295`.

La sonde dense garde 512 lignes et le même pool de 96 caractéristiques.
Elle compare des épisodes à 16 et à 64 symboles distincts, avec tous
les symboles présents. Elle ne représente pas les épisodes à huit
symboles du benchmark habituel.

| Mesure profilée | Linux | Windows |
|---|---:|---:|
| Recherche dense, 16 symboles | 0,143 s | 0,262 s |
| Recherche dense, 64 symboles | 0,517 s | 0,986 s |
| Hypothèses examinées, chaque cas | 5 772 | 5 772 |

Les bits d'ordre vrais passent de 30 602 à 515 728. Dans le cas dense
64, leur préparation devient le coût dominant, alors que le nombre
d'hypothèses scorées reste identique. Une borne de 128 symboles et de
32×1 024 lignes ne signifie donc pas un coût proche de l'essai publié.

**Optimisation proposée :** indexer les prédicats dans une fenêtre
incrémentale ou conserver une représentation d'ordre permettant de
calculer seulement les prédicats nécessaires. Compter la mémoire de cet
index et son coût d'éviction. Conserver exactement la sémantique des
premières occurrences et vérifier la sélection sur les mêmes lignes.
Éliminer des prédicats modifie la capacité de recherche ; cette option
doit être évaluée comme un changement d'algorithme.

### O3 — priorité moyenne : recherches et replay synchrones sous le verrou

[plastic_revision.py:198–219](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/plastic_revision.py#L198)
recherche un programme puis fait quatre passes sur toutes les lignes
pour deux banques. À 4 096 lignes, cela représente **32 768 gradients**
dans un seul retour qui déclenche un fit, en plus de la recherche et
des moyennes. Ces appels ont lieu dans la transaction de l'adaptateur,
pendant qu'il détient son verrou.

Le profil précédent mesure le chemin ordinaire et ne chiffre pas cette
pointe. Les moyennes de durée par cas publiées ne donnent pas les
percentiles de latence d'un événement. Le système n'a donc pas encore
de preuve de temps réel avec une borne de délai.

**Optimisation proposée :** ajustement découpé ou calcul préparé hors de la
transaction, depuis un instantané immuable et une frontière causale
explicite. Toute modification du moment de début de validation doit
conserver la séparation fit/futurs labels, le RNG, les budgets et la
reprise. Une implémentation NumPy ou native du replay peut aussi être
mesurée, mais ne doit pas changer les géodésiques, le budget ni les
critères en silence.

### O4 — priorité moyenne : recherche complète inutile lors du raffinement

[plastic_revision.py:198–203](https://github.com/Setharkk/Remake-setharkk/blob/f6a1ea4f74ac546bed79eef562894320c358790e/first_piece/plastic_revision.py#L198)
exécute `_search` puis remplace son résultat par le programme courant
lorsque `refinement_gain` est fourni. Le travail était annoncé et
compté ; il ne contribue pas au choix du programme de cet essai.

**Optimisation proposée :** préparer directement ce programme après
les gardes de support et de gain, avec un compte rendu honnête de zéro
hypothèse alternative examinée. Les validateurs supposent aujourd'hui
les champs d'une recherche ordinaire : adapter ensemble journal,
restauration et politique de format. Le gain de temps ne doit pas
diminuer les gradients de fit ou supprimer la validation prospective.

### O5 — priorité moyenne : copies de fenêtres et prévisions répétées

`shared.py:504–507` recopie les listes de pertes et de fit à chaque
retour. `calibrated.py:117` fait `pop(0)`, qui décale le cache.
Ces opérations sont bornées, mais leur coût se répète à chaque interaction.

Une fenêtre circulaire ou un deque peut réduire ce travail, avec une
sérialisation canonique et une gestion correcte du label évincé.
Optimiser ces listes avant O1 aura toutefois un effet limité.

Le profil direct compte 1 440 lectures de prototypes et 2 880 distances
pour 96 épisodes. `CalibratedLearner.learn` relit toutes les actions
pour la sortie servie puis pour la sortie brute ; `SharedLearner.learn`
relit l'action sélectionnée et l'update relit sa probabilité.
Les banques de validation étant figées, leurs prévisions par route et
action et leurs logits peuvent être mis en cache pendant l'essai.
Tout cache doit être invalidé au changement de banque et ne jamais
réutiliser une prévision d'une autre révision.

### O6 — priorité basse : reprises et diagnostics coûteux

Dans cette sonde à 4 096 lignes, un checkpoint non profilé prend environ
7,8 ms sous Linux et 16,0 ms sous Windows ; une restauration, checkpoint
d'entrée inclus, environ 77,4 ms et 143,7 ms. Les reprises contrôlent chaque
ordre d'apparition et recomputent les probabilités de calibration. Les
métriques recopient aussi les journaux détaillés.

Ces coûts sont acceptables pour une reprise ponctuelle, mais pas pour
une télémétrie appelée à chaque symbole. Séparer métriques sommaires
et export détaillé, puis mesurer la cadence utile. Les ensembles de
relations légales peuvent être préparés une fois par restauration.
La validation de cohérence ne doit pas être supprimée pour accélérer.

Les boucles `set_bits` se terminent : chaque passage retire un bit.
Les boucles des banques, hypothèses, replay et moyennes ont des bornes
de configuration. Les `while True` des laboratoires attendent une
surface que leurs mondes finis fournissent. La revue n'a pas identifié
de boucle Python infinie sur ces entrées valides. Une attente d'exécuteur
ou de frontière d'épisode relève d'une autre limite ci-dessous.

## Limites restantes

### L1 — couverture des routes et des actions

`shared.py:433–435` vérifie seulement les routes avec un effectif non nul.
La sonde obtient une admission à 512 retours avec le support
`[512, 0]` pour un programme binaire. La seconde route est possible,
mais n'a pas reçu de label de validation.

Il ne s'agit pas d'un contournement de la borne de **gain moyen sur les
entrées observées** : la borne ne promet pas une compétence sur toutes
les routes. C'est une limite de portée et un commentaire trop large
sur le support de toutes les routes atteignables. Il n'existe pas non
plus de seuil de support par paire route/action ; le fit demande
16 lignes par route, pas 16 par action.

La calibration est apprise sur les actions exécutées. Les mesures
publiées utilisent des actions uniformes ; elles ne certifient pas
une politique choisissant presque toujours la même action. Avant
l'exploration autonome, annoncer la couverture et prévoir des
expériences sur actions déséquilibrées et routes rares. Si l'on
renforce la garde, déclarer l'effet sur le délai d'admission.

### L2 — grammaire et recherche bornées

Présences, ordres de premières occurrences et égalités de contexte sont
les seuls prédicats. Le programme utilise au plus trois variables, donc
huit routes. Il ne représente ni les répétitions, ni les intervalles
physiques, ni des séquences arbitraires, ni un langage naturel appris.

Le pool de 96 caractéristiques et le faisceau de 12 paires sont des
réglages par défaut. Certaines variables pertinentes peuvent être
écartées. Une interaction de trois variables sans gain marginal peut
être manquée avant toute admission ; la continuité d'un programme
ancien atténue ce problème sans rendre la recherche exhaustive.

Les 16 contextes du benchmark partagent une règle avec une exception.
Les résultats ne prouvent pas une capacité pour 16 tâches indépendantes.
Ces limites relèvent de la première pièce si la suite demande davantage
de pouvoir de représentation.

### L3 — mémoire récente et risque à vie

Le buffer est borné, donc des cas anciens peuvent disparaître. Une seule
banque protégée commune est conservée ; il n'y a pas un catalogue de
compétences générales ou de mondes antérieurs.

Le risque sommable rend les admissions ultérieures plus exigeantes et
chaque essai garde un horizon final fini. « Recherche renouvelable »
ne garantit donc pas que toute amélioration faible sera un jour admise.
L'âge du neurone réduit aussi le pas des banques de travail. Les candidats
redémarrent leurs compteurs, mais le comportement sur des historiques
beaucoup plus longs, du bruit corrélé et des dérives lentes reste à mesurer.

### L4 — ressources déclarées et ressources physiques

96 points S² en service et 160 pendant un essai décrivent les banques
logiques avec quatre actions et huit routes. Avec seize actions, ce
budget devient 384 et 640 points. Les buffers et la recherche augmentent
aussi avec les capacités configurées.

La transaction conserve temporairement le modèle source et sa copie.
Les nombres logiques de points ne comptent pas toutes ces duplications.
La taille JSON ne mesure pas la RAM du processus, ses objets Python,
ses bitsets temporaires ou les évaluations. Aucun budget de RAM mesuré,
aucun percentile de latence et aucun entraînement GPU ne sont fournis
par les expériences actuelles.

### L5 — frontière d'intégration encore séquentielle

Un seul flux, un épisode en cours et une action en attente sont assumés.
Il n'y a ni timeout physique, ni résultat tardif concurrent, ni remise
en ordre de plusieurs flux, ni éviction de contexte/vocabulaire une fois
le budget rempli. Une observation sans fermeture ou un reçu qui ne revient
pas peut bloquer le flux jusqu'à intervention de l'appelant.

Les objectifs autonomes, dialogue, planificateur, essaim, capteurs PC
et journal durable d'exécution restent absents. Le checkpoint protège
une frontière locale et ne garantit pas qu'une action physique ne sera
pas exécutée deux fois après une panne. Ces fonctions relèvent du
coordinateur et des exécuteurs ; leurs préconditions doivent être
spécifiées avant de dépendre du cœur.

### L6 — portée scientifique et couverture des mesures

Les mêmes familles de règles et quelques graines ont servi aux révisions.
Les deux graines supplémentaires sont une extension modeste, pas une
preuve de généralisation. Les scores de politique sont des sondes finies,
pas des garanties universelles.

L'ablation ne démontre pas d'avantage propre au transfert de poids.
Le système reste neuronal et symbolique : les petits budgets de points
n'effacent pas le rôle des prédicats et des buffers. Aucun test comparable
n'isole une supériorité de S² sur un réseau euclidien. La revue ne trouve
aucune base pour revendiquer un paradigme inédit à partir de ces scores.

## Confrontation à la spécification

| Exigence ou promesse | État observé | Action nécessaire |
|---|---|---|
| Paramètres neuronaux réellement non euclidiens | Points S², distances et gradients géodésiques présents | Corriger B2 en gardant cette géométrie |
| Une autorité d'apprentissage, reçus répétés sans double gradient | Présent dans les contrats et tests | Conserver la propriété pendant les corrections |
| Copie transactionnelle isolée et reprise cohérente | Contredite par B1 dans le mode plastique | Correction prioritaire du journal mutable |
| Domaine utilisable de chaque prototype transféré | Pas assuré après la moyenne, B2 | Vérification avant replay |
| Délai confirmé ≤12 000 dans le protocole | Chiffres publiés conformes, critère programmé trop faible, B3 | Tester la confirmation |
| Validation prospective avec risque déclaré | Banques figées, regards et dépenses explicites | Conserver les hypothèses ; ne pas élargir à toutes les routes/actions |
| Apprentissage continu avec mémoire bornée | Implémenté sur des épisodes et capacités bornés | Mesurer dérive lente, historiques longs et tâches indépendantes |
| Petit budget de paramètres | Vrai pour les points neuronaux, coût total plus large | Budgets séparés pour mémoire, copies, recherche et délais |
| Temps réel | Pas de limite numérique ni de latence de pointe mesurée | Fixer un budget puis mesurer la queue de latence |
| Raccord au cortex et agents | ABI version 1 disponible, flux séquentiel | Définir continuations et contraintes du coordinateur |
| Dialogue, buts et actions PC | Explicitement à développer | Ne pas les comptabiliser comme acquis |

La spécification est surtout une chronologie de modes et de protocoles.
Elle ne fixe pas encore de contrat de performance pour la première pièce
actuelle : seuils de débit, latence maximale, RAM du processus, couverture
des actions et délai de récupération sur entrées non uniformes. Écrire
ces critères avant leur prochaine mesure évite de juger trop tôt et
d'adapter les critères aux résultats.

Deux détails documentaires devraient aussi être alignés : la section
consolidée de `SYSTEM_ARCHITECTURE.md` parle encore du « format 6
ci-dessous », alors que la section plastique décrit le format 7 ;
`first_piece/README.md` présente les modes temporel et présence sans
pointer directement vers le moteur actuel. Les anciens workflows de revue
et leurs seuils appartiennent à leurs références historiques ; leur nom
« current » ne suffit pas à en faire des contrôles du format 7.

## Ordre de correction compatible avec les pièces suivantes

1. Corriger B1 et B2, avec tests de rollback tardif, reprises et domaine
   géométrique. Garder identités, causalité et budgets lorsqu'ils sont
   compatibles ; versionner toute modification de politique sérialisée.
2. Corriger B3 et préciser la couverture de L1. Distinguer premier
   succès, confirmation, route observée, action observée et score calibré.
3. Réduire O1 avec une propriété explicite des objets mutables, puis
   O4 et O5. Vérifier parité direct/adaptateur et reprise avant de
   publier de nouveaux gains.
4. Mesurer les pointes de O3 et les cas denses de O2 avec des budgets
   CPU et RAM. Planifier une interface de continuation avant toute
   concurrence d'agents ; conserver un instant de début prospectif.
5. Étendre les tâches et l'exploration seulement avec des exigences
   communes au cœur et au coordinateur. Traiter B4 et les références
   historiques séparément de la capacité du moteur actuel.

Les deux P1 empêchent de considérer la frontière actuelle comme robuste
face à une opération avortée ou à tous les transferts géométriquement
admissibles. Ils doivent être résolus avant que la deuxième pièce
s'appuie sur cette garantie.
