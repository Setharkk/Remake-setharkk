# Conservation de compétences et validation : résultats

**Les deux échecs précédents sont corrigés dans le protocole testé : la compétence
reste accessible après le bruit, et les six changements du contexte minoritaire
sont admis. Les probabilités sont toutefois moins bien calibrées pendant le bruit,
et une première admission après bruit devient plus lente.**

[Moteur testé c4ae931](https://github.com/Setharkk/Remake-setharkk/commit/c4ae9316fa84e051274c79887114147a9cdda502).
[Workflow Windows/Linux](https://github.com/Setharkk/Remake-setharkk/actions/runs/37227342820).
[Protocole fixé avant exécution](CONSOLIDATION_PROTOCOL.md).
[Utilisation et reprise](CONSOLIDATION.md).
[Échecs du mode précédent](RENEWABLE_SEARCH_RESULTS.md).

## Vérifications et mesures

**113 tests réussissent sous Windows et Linux**, dont conservation des poids
protégés sous bruit, reprise exacte d'une admission ciblée, import de validations
historiques, requête en attente et reçu appris une fois, corruption des largeurs,
horizons et compteurs. Le test de signal faible exige et observe une admission
après un regard au-delà de 4 096 retours.

Les quatre workflows historiques passent aussi, sans modifier leur comportement
attendu : laboratoire, six corrections, montée à l'échelle, renouvellement/rétention.
Le code des modèles historiques garde leurs formats, budgets et critères.

Trois graines 0, 1, 2 ; 16 symboles opaques, quatre contextes et quatre actions.
Chaque moteur traite 1 500 000 retours d'apprentissage par OS, les mêmes événements
et actions exploratoires uniformes. Les deux moteurs traitent donc 3 000 000 retours,
sur 1 500 000 épisodes communs ; les gradients de replay sont comptés séparément.
642 points d'évaluation comportent chacun 2 048 épisodes sans apprentissage :
1 314 816 épisodes d'évaluation par OS.

Le succès publié est celui de l'action de probabilité maximale dans l'évaluation.
Les actions d'entraînement sont uniformes : leur succès observé reste proche de
25 % même après acquisition. Les deux OS répètent les mêmes graines, pas six
répétitions indépendantes. Les modifications sont comparées conjointement ;
cet essai n'est pas une ablation isolée de chaque mécanisme ni de la courbure.

## Conservation après 80 000 retours aléatoires

20 000 retours structurés, puis 80 000 aléatoires, puis 40 000 structurés.
L'évaluation examine l'ancienne règle sur un flux nouveau, sans apprentissage.

| Graine | Mode renouvelable après bruit, contextes 0/1/2/3 | Mode protégé après bruit |
|---|---|---|
| 0 | 0 / 0 / 0 / 0 % | 100 % dans chaque contexte |
| 1 | 0 / 0 / 0 / 0 % | 100 % dans chaque contexte |
| 2 | 26,76 / 24,61 / 26,56 / 20,51 % | 100 % dans chaque contexte |

La réussite reste à 100 % à chacune des quatre mesures pendant le bruit dans
le mode protégé. Aucune nouvelle admission n'intervient pendant ces phases :
le programme et les points protégés conservent la dernière compétence validée.
Les banques de travail continuent de recevoir des gradients.

Au retour des retours structurés, le mode protégé reste à 100 % dès la première
mesure. Le modèle renouvelable récupère aussi 100 %, mais après de nouveaux
retours ; sa récupération ne constituait pas une conservation.

## Six changements successifs appris

La règle du seul contexte 0 suit 0 → 1 → 2 → 3 → 0 → 2 → 1.
Chaque état dure 40 000 retours globaux, 10 000 par contexte.

Le nouveau mode finit **chacune des six phases à 100 % dans les quatre contextes,
pour les trois graines**. Les contextes 1–3 restent à 100 % à chaque point mesuré.
Il réalise sept admissions par graine : l'acquisition initiale et six remplacements.
Le mode renouvelable reste à une admission et à 0 % dans le contexte modifié
à la fin des phases de décalage non nul.

Les délais ci-dessous comptent les retours du contexte 0 depuis le changement,
jusqu'à l'admission. Ce sont des délais mesurés d'admission, pas le premier
instant exact de réussite. Les courbes montrent aussi les échecs transitoires.

| Graine | →1 | →2 | →3 | →0 | →2 | →1 |
|---|---:|---:|---:|---:|---:|---:|
| 0 | 4300 | 4295 | 4294 | 4293 | 4295 | 4297 |
| 1 | 4296 | 4295 | 4297 | 4303 | 7361 | 4297 |
| 2 | 4298 | 4293 | 4301 | 6133 | 4297 | 4297 |

Ces épisodes structurés suffisent dans le protocole annoncé, sans rallonger les
phases après les résultats. Ils ne démontrent pas l'adaptation à des règles
arbitraires, à davantage de prédicats ou à des changements plus rapides.

## Pourquoi la garde peut décider

Graine 0, tentative 3, retour global 57 197 : même date que l'exemple de blocage
historique, mais la banque servie est maintenant protégée.

| Mesure | Valeur |
|---|---:|
| Retours principaux | 4 096 |
| Retours du complément | 12 288 |
| Borne inférieure de pertinence | 0,16300 |
| Borne inférieure d'amélioration | 1,91023 |
| Largeur conditionnelle de conservation fixée avant validation | 0,09039 |
| Gain moyen de conservation | +0,000069 |
| Rayon de la borne uniforme | 0,002633 |
| Borne inférieure de conservation | −0,002564 |
| Seuil requis | strictement supérieur à −0,10 |

La largeur universelle des gains vaut 9,21034. Quand les deux réseaux sont figés,
la différence de leurs log-odds permet une largeur bien plus petite sur les
routes du complément. Elle est calculée avant les nouveaux résultats, en incluant
toutes les paires de routes possibles et tous les slots de la capacité.
La borne n'est pas rétrécie à partir du résultat souhaité.

Pour certaines admissions, les probabilités tronquées des deux réseaux sont
identiques sur toutes les routes du complément : le gain tronqué est alors
déterministement nul, et sa largeur conditionnelle vaut zéro.
Cela ne signifie pas que toutes les probabilités brutes sont identiques.

Les regards 8 192 et 16 384 conservent des essais qui auraient été clos plus tôt.
Dans le bruit-initial graine 2, l'admission utilise effectivement 8 192 retours
principaux. Les changements ci-dessus sont admis au regard 4 096.
Le risque du bloc est réparti sur cinq regards ; le total à vie n'est pas augmenté.

## Régressions et compromis

**Calibration pendant le bruit.** Les probabilités protégées conservent l'ancienne
règle ; les résultats actuels sont pourtant Bernoulli(1/4), indépendants.
Le Brier sur ces retours réels est donc moins bon. Valeurs sur les 80 000 retours
de bruit après acquisition, score de l'action exploratoire choisie :

| Graine | Brier renouvelable | Brier protégé | Perte logarithmique renouvelable | Perte logarithmique protégée |
|---|---:|---:|---:|---:|
| 0 | 0.19193 | 0.36904 | 0.57781 | 1.73306 |
| 1 | 0.19202 | 0.37033 | 0.57779 | 1.72587 |
| 2 | 0.19006 | 0.36628 | 0.57363 | 1.71227 |

La référence constante p=1/4 a un Brier attendu de 0,1875.
La protection préserve l'information de la compétence ; elle ne fournit pas
encore une confiance qui s'ajuste à la fiabilité du monde actuel.

**Admission après bruit initial.** Après 40 000 retours aléatoires et 40 000
structurés, les deux modes finissent à 100 % dans chaque contexte, sans admission
sous bruit. Mais le délai de première admission change :

| Graine | Mode précédent, retours globaux de signal | Nouveau mode | Regard utilisé dans le nouveau mode |
|---|---:|---:|---:|
| 0 | 8 640 | 20 928 | 4 096 |
| 1 | 4 672 | 4 672 | 4 096 |
| 2 | 8 896 | 8 640 | 8 192 |

Un essai peu utile mais encore positif peut rester ouvert plus longtemps avec
les nouveaux horizons. Un budget prolongé n'accélère donc pas tous les cas.
La qualité du Brier pendant la phase structurée varie aussi : après consolidation,
les probabilités servies ne sont plus affinées par chaque gradient intermédiaire.

**Voie plastique.** Les poids de travail continuent d'apprendre, mais les candidats
sont encore réinitialisés et ajustés sur les buffers récents. Ces poids plastiques
ne servent pas à initialiser les candidats dans cette version. Les intégrer,
ou supprimer une voie devenue redondante, doit préserver les comparaisons de
budget, la signification des routes et les invariants de reprise.

## Coûts, reprise et plateformes

La copie ajoute une banque de 32 points S². Après acquisition, 96 points en service
avec banques de travail et contrôle, 160 pendant une validation, soit
192/320 degrés de liberté intrinsèques. Avant la première admission, la banque
protégée n'est pas encore allouée. Les contextes n'allouent pas de réseaux privés.

Dans les neuf conditions : au plus 16 recherches détaillées, 30 décisions observées
dans le mode protégé (borne 80), 1 024 lignes retenues pour l'ajustement,
160 points maximum. Le maximum JSON échantillonné vaut 92 283 octets Windows,
92 284 Linux ; ce n'est pas une mesure du pic de mémoire Python.

Les checkpoints restaurés en cours de validation ciblée et après renouvellement
reproduisent 1 024 retours futurs, état identique sauf durée de recherche.
L'import depuis le format 3 conserve les validations déjà commencées avec leurs
anciens horizons ; la nouvelle frontière de politique est explicite.
Les tests vérifient aussi requête en attente et reçu répété.

Windows Python 3.11.9, Linux Python 3.11.16.
79 346 valeurs numériques comparées ;
écart maximal 5.329e-15, tolérance 1e−10,
zéro divergence. Durées, tailles JSON, version Python et runner exclus.
Les neuf cas prennent 532,62 s Windows et 752,90 s Linux, deux moteurs et
évaluations inclus. Les CPU et charges de runners diffèrent ; ce n'est pas
une mesure de la RTX du PC.

## Données complètes et limites

- [Index Windows](consolidation_results/windows/index.json)
- [Index Linux](consolidation_results/linux/index.json)
- [Comparaison des plateformes](consolidation_results/comparison.json)

Les index contiennent métadonnées et résumés, puis référencent les neuf fichiers
par condition/graine. Toutes les phases, courbes, scores réels, journaux, bornes,
reprises et métriques finales y sont conservés. Les artefacts du workflow
contiennent aussi les rapports uniques exportés par le CLI.

La prochaine limite mesurée est la confiance des probabilités sous bruit,
à traiter sans effacer la compétence protégée. La durée des essais peu utiles
et la voie plastique doivent également être étudiées. Le mode protégé n'a ici
été testé qu'à 16 symboles et quatre contextes ; les essais historiques plus
grands concernent le moteur partagé de référence.

Restent la famille de prédicats fournie, les trois prédicats maximum, l'horizon
encore borné et l'absence de comparaison euclidienne à capacité identique.
Les objectifs autonomes, le dialogue, l'essaim et les applications PC restent
à construire. Ce résultat est une correction expérimentale de la première pièce,
pas une démonstration d'un world model général.
