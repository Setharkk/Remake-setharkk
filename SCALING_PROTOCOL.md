# Première pièce : protocole de montée à l’échelle

Protocole fixé avant les mesures de cette version. L’objectif reste une preuve d’apprentissage dans un environnement synthétique. Il ne s’agit pas encore d’un cortex autonome ou d’un exécuteur Windows.

## Hypothèse testable

Un seul modèle sphérique partagé entre les contextes peut apprendre des combinaisons de relations observables, transférer la même règle à un contexte neuf, et adapter un contexte minoritaire sans dégrader excessivement les autres.

Les vrais paramètres neuronaux sont des points sur S². Le routage discret combine au maximum trois prédicats binaires : présence d’un symbole, ordre de première occurrence entre deux symboles, égalité d’un contexte observable. Ni opérateur XOR spécifique, ni règle du monde, ni annonce de changement n’entrent dans le modèle. La famille de prédicats est néanmoins programmée : ce n’est pas une découverte d’un paradigme inédit.

## Budgets

- 2 à 16 actions ; 1 à 32 contextes ; 4 à 128 symboles opaques, liés dynamiquement.
- Par contexte : au plus 256 épisodes d’ajustement par défaut et 64 pertes récentes ; aucun poids neuronal privé.
- Jusqu’à 3 prédicats ; 8 routes et 4 actions dans les deux grandes conditions : 32 points dans le modèle, 32 dans le contrôle, soit 128 degrés de liberté intrinsèques en service, indépendamment du nombre de contextes.
- Pendant une validation, deux banques figées supplémentaires : au plus 128 points / 256 degrés de liberté intrinsèques. Les banques en service continuent d’apprendre.
- Recherche : au plus 96 prédicats par défaut, tous les couples et extensions des 12 meilleurs couples et des au plus 3 couples du programme déjà admis en triples. Budget global de 16 essais. Un XOR de trois variables peut échapper à cette recherche par faisceau.
- Ajustement des deux banques proposées sur exactement les mêmes anciennes données, quatre passages mélangés. Résumés de validation de taille fixe ; aucune conservation de toutes les interactions.
- Les grandes mémoires binaires sont sérialisées en chaînes hexadécimales canoniques, compatibles avec JSON et JavaScript.

## Admission prospective

Le modèle proposé et son contrôle sont fixés avant les nouvelles observations utilisées pour décider. Le contrôle possède le même nombre de points et le même nombre de mises à jour, avec un routage aléatoire indépendant des observations. Deux gains de score logarithmique sont mesurés : pertinence contre ce contrôle, amélioration contre la prédiction effectivement servie avant le retour.

Sans composition admise, la validation porte sur tout le flux. Ensuite, un essai est déclenché sur un contexte dont l’erreur récente est élevée ; ce périmètre est fixé avant sa validation. Les autres contextes servent de garde de conservation : borne inférieure du gain supérieure à −0,1 nat par observation. Ce seuil est une tolérance de score, pas une garantie de zéro oubli.

Horizons du périmètre principal : 128, 1 024 et 4 096 retours. Probabilités d’issue bornées dans [0,01 ; 0,99]. Borne conditionnelle de Hoeffding-Azuma pour les gains prédictibles bornés, avec allocation conservatrice de α=0,05 à 3 comparaisons × 3 horizons × 16 essais par moteur. Il s’agit d’un contrôle des décisions sur les blocs observés ; ni garantie future ni α global de toute l’étude. Coût : 0,005 nat par prédicat. Minimum de 16 observations par route effectivement observée dans le périmètre. Un arrêt de futilité empirique n’est pas une preuve statistique d’impossibilité.

## Mesures prévues

Trois échelles :
1. 8 symboles, 2 contextes, 2 actions ; résultat caché fondé sur deux relations d’ordre (XOR).
2. 32 symboles, 8 contextes, 4 actions ; deux relations déterminent une action parmi quatre.
3. 64 symboles, 16 contextes, 4 actions ; même forme de règle.

Trois graines d’entraînement, répartition alternée des contextes, actions d’exploration indépendantes et uniformes. Même source pour les observations et les retours du modèle et du contrôle. Chaque échelle reçoit 10 000 interactions **par contexte**, puis un changement non annoncé de l’action correcte dans le seul contexte 0, puis 10 000 interactions supplémentaires par contexte.

Évaluations sans mise à jour après 100, 1 000 et 10 000 retours par contexte, avant et après changement. Rapporter séparément contexte changé, autres contextes, contexte neuf, modèle complet, contrôle de capacité identique, intervention d’effacement de l’ordre. Une erreur au premier horizon n’est pas un échec définitif.

Rapporter réussite de la politique, score de Brier sur toutes les actions, interactions globales et par contexte, nombre de paramètres réellement alloués, données mémorisées, essais, hypothèses examinées, mises à jour, temps de recherche et d’entraînement, taille JSON du checkpoint. La taille JSON n’est pas la consommation RAM. Mesurer aussi le coût de l’adaptateur transactionnel, dont la copie transactionnelle doit conserver l’isolation des objets mutables sans recopier récursivement les anciens enregistrements immuables.

Les tests Windows et Linux portent sur les mêmes entrées et graines. Une validation finale utilise de nouvelles graines d’évaluation sans entraînement supplémentaire. Les résultats, y compris les échecs d’adaptation ou le coût de recherche, doivent être conservés.

## Limites du protocole

Alphabet discret, épisodes scellés, retours binaires, une action en vol. Ni images, ni fichiers réels, ni dialogue, ni objectifs autochoisis. L’exploration uniforme et les frontières d’épisode sont fournies. La courbure est effective dans les neurones, mais son avantage sur un modèle euclidien de même capacité reste à établir. Étendre ces bornes ne démontre pas une intelligence générale.

## Révision après le premier essai (source 6855d5a)

Le premier essai a passé 80 tests mais a échoué pendant la grande condition au contrôle de taille du journal. La cause était une répétition d’un examen au même horizon principal, à chaque observation du complément. Cela violait aussi l’allocation préannoncée des comparaisons. Correction : seul un nouveau retour du périmètre principal autorise un examen.

Sur les trois graines de la petite condition, l’apprentissage initial réussissait mais le changement produisait un XOR de trois variables, invisible au faisceau de couples. La recherche corrigée étend aussi les couples du programme déjà admis, dans un budget fixe. Cette continuité est générique et ne donne pas au moteur la règle du monde. Elle ne résout pas la découverte initiale de n’importe quel XOR de trois variables.

Les rapports partiels de cette source sont conservés comme diagnostic et ne constituent pas une validation de la décision statistique. La nouvelle version garde les mêmes tailles, horizons, tolérances et graines d’entraînement. La validation finale emploie les graines d’évaluation réservées, jamais utilisées par le premier essai interrompu.

## Révision du coût de l’interface (après source 1494f58)

Le second essai complet Windows réussit, mais la copie récursive coûte environ 8,5–9,0 ms par épisode dans la petite condition, 28–29 ms dans la moyenne et 53–54 ms dans la grande, contre un cœur direct beaucoup plus rapide. Ces temps concernent les runners GitHub et non le PC de l’utilisateur.

L’adaptateur partagé emploie maintenant une copie transactionnelle spécialisée : RNG, vocabulaire, dictionnaires de contexte, listes de mémoire, banques neuronales et résumé de validation sont isolés ; les anciens enregistrements et décisions, jamais modifiés par le cœur, sont partagés en lecture. Les snapshots publics restent entièrement détachés. Les adaptateurs historiques gardent leur copie récursive. Les tests et la comparaison de l’interface avec le cœur direct vérifient les prédictions et l’état appris.

Cette optimisation ne change ni les données d’entraînement, ni les critères d’admission. Les mêmes essais sont reproduits pour mesurer son coût et vérifier l’identité numérique.

## Revue de l’ordonnancement des futurs agents

Dans le benchmark alterné, le nombre de retours du complément est déterminé à chaque horizon principal. Dans une utilisation future, il pourrait dépendre de l’ordonnancement des agents. Une borne fixe au nombre observé ne suffirait alors pas. La garde de conservation utilise désormais une borne de Hoeffding maximale raccordée sur les intervalles [2^k, 2^(k+1)), avec allocation 6/(π²(k+1)²) entre intervalles. Elle est uniforme dans le temps et conserve l’allocation globale précédente ; elle peut attendre plus longtemps que la garde fixe.

Pour n retours complémentaires, k=floor(log2 n), N=2^(k+1), M=3×3×16, la demi-largeur vaut :
log(1/ε) × sqrt(2 N [log(2M/α)+log(π²/6)+2log(k+1)]) / n.
Les deux tests principaux gardent leurs horizons préannoncés. Avec un seul contexte effectivement observé, l’essai porte sur tout le flux et n’attend pas de complément inexistant.

## Révision après le holdout indépendant à 40 millions

Les contextes déjà observés atteignent la réussite parfaite, mais deux graines de la petite condition échouent sur le contexte neuf après changement. Avec seulement deux contextes, « contexte 0 modifié » et « contexte 1 conserve la règle » définissent des partitions complémentaires équivalentes sur les données ; un écart d’arrondi de score pouvait choisir le mauvais défaut pour un troisième contexte.

La recherche départage maintenant les scores indiscernables à 10^−12 en privilégiant une exception dans le périmètre d’erreur fixé avant validation. C’est un biais de continuité explicite : il conserve le défaut de la règle commune quand deux solutions expliquent les mêmes données. Cela ne révèle pas la règle d’un contexte vraiment inconnu et ne garantit pas son comportement. Les deux permutations de numérotation sont testées.

Les seuils, capacités et budgets de validation ne sont pas changés. Le holdout de 40 millions est conservé comme diagnostic ; la version corrigée sera vérifiée avec un nouveau holdout de 50 millions.

## Livraison mesurée

La version finale est testée à la source 5745cb5, workflows 37214331488
et 37214331510. Le holdout réservé à 50 millions et les contrôles de bruit
sont exécutés par la source fa83c8c, workflow 37214674910.
Le [rapport](FIRST_PIECE_SCALE_RESULTS.md) publie les résultats et conserve
les diagnostics précédents, sans fusionner leurs échantillons avec le holdout final.
