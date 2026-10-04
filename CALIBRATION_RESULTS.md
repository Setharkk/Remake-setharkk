# Calibration sans effacement : résultats

**La surconfiance sous bruit est réduite dans les douze conditions testées.
La compétence protégée, les gradients, le RNG et les admissions restent ceux
du mode consolidé. Les probabilités retrouvent leur contraste après de nouveaux
retours structurés.**

[Moteur testé](https://github.com/Setharkk/Remake-setharkk/commit/bf15bec840136291ce52892c3f5a0824cdf72f5b).
[Workflow Windows/Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37230529059).
[Protocole fixé avant mesure](CALIBRATION_PROTOCOL.md).
[Utilisation et formules](CALIBRATION.md).

## Vérification et périmètre

124 tests passent sous Windows et Linux. Les onze nouveaux tests couvrent
l'amélioration des scores sous bruit, les taux de bruit appris par contexte,
l'identité de l'apprentissage brut, la chauffe d'un nouveau contexte,
les copies privées, les corruptions du cache et des moments,
les prévisions en attente, leur clôture sans résultat et les reçus répétés.

Les cinq workflows déclenchés passent sur les deux plateformes :
calibration, consolidation, renouvellement, corrections et laboratoire.
La référence de montée à l'échelle n'a pas changé ; son workflow antérieur
reste une preuve de ce moteur historique.

12 conditions, graines 0/1/2, 16 symboles, quatre contextes, quatre actions.
Chaque moteur reçoit 1 620 000 retours par OS, soit 3 240 000 pour les deux
moteurs sur 1 620 000 épisodes communs. Les gradients de replay restent comptés
séparément. 708 points d'évaluation de 2 048 épisodes représentent
1 449 984 épisodes de sonde par OS.

Les actions d'apprentissage sont exploratoires et uniformes.
La sonde de conservation évalue l'ancienne règle structurée sur de nouveaux
épisodes, sans apprentissage ; ses 100 % ne sont pas un succès à 100 % dans
un monde donnant des résultats aléatoires. Le Brier et la perte logarithmique
sur les retours réellement reçus évaluent ce monde courant.
La perte logarithmique est tronquée à 0,01 comme dans le protocole précédent.

Les OS reprennent les mêmes graines ; il s'agit de trois répétitions
indépendantes et d'une vérification de reproductibilité, pas de six graines.
Les résultats ne démontrent pas une supériorité de la courbure.

## Surconfiance pendant 80 000 retours bruités

Après 20 000 retours structurés, le monde donne 80 000 résultats indépendants
Bernoulli(1/4), puis 40 000 retours structurés. Scores calculés AVANT chaque
résultat, sur l'action réellement exécutée :

| Graine | Brier protégé non calibré | Brier calibré | Perte tronquée non calibrée | Perte tronquée calibrée |
|---|---:|---:|---:|---:|
| 0 | 0,369038 | 0,189144 | 1,733057 | 0,567706 |
| 1 | 0,370329 | 0,189295 | 1,725872 | 0,567717 |
| 2 | 0,366281 | 0,187320 | 1,712273 | 0,563626 |

La référence constante p=1/4 a un Brier attendu de 0,1875.
Les trois graines respectent les seuils fixés avant exécution :
Brier <= 0,205 et perte tronquée <= 0,62.

Aucune nouvelle admission sous bruit. Les programmes et points protégés
restent inchangés. La sonde de l'ancienne règle garde 100 % dans chaque
contexte à chaque mesure. Le mélange est croissant en p, avec un contraste
minimum positif : ce maintien de l'argmax ne prouve donc pas la calibration.
Les scores probabilistes ci-dessus constituent la mesure distincte.

## Retour d'une règle fiable

À la première sonde après le retour du signal, soit 2 000 retours globaux,
500 par contexte, le contraste c est revenu à 1 dans tous les contextes
et les trois graines. La prévision calibrée est alors la prévision brute.

Le Brier structuré par contexte se situe entre 0,00007199 et 0,00007811,
très inférieur au seuil annoncé de 0,025. Ce point de mesure ne donne pas
le premier instant exact de récupération. La fenêtre de 256 retours
par contexte explique qu'une calibration ait besoin de nouveaux résultats.

Une limite mesurée accompagne cette correction : pendant le bruit, les
probabilités calibrées appliquées à une sonde qui suppose l'ancienne règle
structurée donnent un Brier de 0,12628 à 0,19141, contre environ 0,00007
pour la mémoire brute. Elles reflètent le monde récemment observé et
ne retrouvent leur contraste qu'après ses retours redevenus structurés.
L'information de l'ancienne règle reste accessible dans la banque brute.

## Taux de bruit variables

Trois conditions supplémentaires utilisent 20 000 retours structurés,
12 000 retours indépendants à taux 0,1 pour les contextes 0–1 et 0,6 pour
2–3, puis 8 000 structurés.

Scores sur les 8 000 derniers retours bruités, comme annoncé :

| Graine | Brier non calibré | Brier calibré | Perte tronquée non calibrée | Perte tronquée calibrée |
|---|---:|---:|---:|---:|
| 0 | 0,403100 | 0,164746 | 1,891762 | 0,498207 |
| 1 | 0,417493 | 0,167410 | 1,947439 | 0,505718 |
| 2 | 0,415475 | 0,164412 | 1,943080 | 0,497202 |

Les seuils Brier <= 0,26 et perte <= 0,58 sont respectés.
Les taux ne sont pas imposés à 1/action_count. En fin de bruit, l'écart
maximal entre le taux estimé b et le taux réel est 0,096094 :
le contexte 2 de la graine 0 estime 0,503906 au lieu de 0,6.
Une fenêtre courte conserve donc des fluctuations. Le contraste résiduel
peut atteindre 0,101859 dans ces sondes ; aucune certitude épistémique
n'est fournie par ce coefficient.

La sonde de compétence reste à 100 %, sans nouvelle admission sous bruit.
La récupération à 500 retours par contexte respecte aussi le seuil annoncé.

## Apprentissage de compétence conservé

Les six changements du seul contexte 0 suivent 0 → 1 → 2 → 3 → 0 → 2 → 1.
Chaque phase finit à 100 % dans les quatre contextes et les trois graines,
avec sept admissions : acquisition initiale et six remplacements.
Les autres contextes restent corrects aux points mesurés.

À chaque fin de phase, la totalité du checkpoint de compétence est identique
entre les deux modes : programme, toutes les banques, comptes de gradients,
RNG, buffers, risque, validation et histoire, hors identité du mode,
calibration et durée de recherche. Les journaux complets de recherches et
décisions sont aussi comparés et identiques, durée exclue. Les archives
bornées du cœur ne masquent donc pas une divergence du journal collecté.

Les déclencheurs et comparaisons prospectives continuent à examiner la
compétence brute. Le calibrateur adaptatif n'utilise pas les bornes de
cette validation comme une garantie sur ses propres prévisions.

La lenteur d'une première admission après bruit initial reste inchangée :
20 928, 4 672 et 8 640 retours globaux de signal pour graines 0/1/2.
Cette correction de calibration ne réduit pas ce délai ni ne rend les
poids de la voie plastique utiles à l'initialisation des candidats.

## Ressources, reprise et plateformes

Le nombre de paramètres neuronaux ne change pas : 96 points S² en service
après admission, avec travail et contrôle, 160 pendant une validation,
soit 192/320 degrés de liberté intrinsèques. Les paramètres dérivés b et c
sont des statistiques, avec 1 024 probabilités en cache et 16 sommes au
maximum dans cette configuration. Leur stockage est compté séparément.

Maximum observé : 16 recherches détaillées, 30 décisions (borne 80),
1 024 exemples retenus pour le fit, 160 points S².
Le maximum JSON échantillonné vaut 113 694 octets Windows et 113 699 Linux.
Il ne mesure pas le pic de mémoire Python. Les douze cas prennent 926,05 s
Windows et 708,53 s Linux. Les CPU et charges de runners diffèrent ; ces
durées ne sont pas une mesure de la RTX du PC.

Python 3.11.9 sous Windows, 3.11.16 sous Linux.
89 277 valeurs numériques comparées,
écart maximal 5.329e-15,
tolérance 1e−10 : aucune divergence. Durées, tailles JSON, runner et version
Python sont exclus de cette comparaison. Les 24 paires de journaux
compétence/calibration (12 par OS) sont identiques, durée exclue.

Le cache est reprojeté sur les épisodes passés après chaque admission.
Il consomme des calculs supplémentaires, sans gradient neuronal et sans
donnée future. Les temps totaux incluent deux moteurs, reprises et sondes ;
ils n'isolent pas le coût du calibrateur.

Toutes les reprises ciblées et après renouvellement vérifient 1 024 retours
futurs, état identique sauf durée de recherche. Les tests couvrent aussi
prévision en attente, import, reçu répété et clôture sans apprentissage.
Le format 5 et la nouvelle identité rendent la conversion explicite.

## Données complètes et limites restantes

- [Index Windows](calibration_results/windows/index.json)
- [Index Linux](calibration_results/linux/index.json)
- [Comparaison numérique et journaux](calibration_results/comparison.json)

Les index référencent les douze cas complets avec phases, courbes, scores,
journaux, reprises et métriques. La recomposition des cas restitue exactement
le rapport JSON original, hors les champs de packaging ajoutés à l'index.
Les artefacts du workflow contiennent aussi les rapports CLI uniques.

La calibration dépend d'une fenêtre finie, mélange les sous-régions d'un
contexte et reste sensible aux fluctuations et changements rapides.
La sélection uniforme d'actions est une limite des mesures : une politique
différente peut changer b et les observations disponibles ; aucune correction
par propension n'est fournie. Aucun intervalle de confiance épistémique
n'est estimé par cette lecture.

Les banques plastiques restent mises à jour sans initialiser les candidats.
Leur coût et la latence d'admission restent à traiter. Les observations,
frontières d'épisode et famille de prédicats sont fournies ; trois prédicats
maximum et un horizon encore borné. Le nouveau mode n'est mesuré ici qu'à
16 symboles et quatre contextes.

Le dialogue, le cortex coordinateur, les objectifs autonomes, l'essaim
et les applications PC restent à construire. La correction conserve le
réseau géométrique et améliore les scores dans le protocole annoncé ;
elle ne constitue pas une innovation scientifique démontrée ni un
world model général.
