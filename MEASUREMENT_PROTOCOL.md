# Mesurer l'apprentissage et choisir la durée d'un essai

La durée et les unités de mesure font partie du protocole de recherche.
Un résultat observé à un budget donné ne décrit pas tous les budgets possibles.

## Ce que l'on mesure

L'objectif initial discuté est de découvrir une règle inconnue et de la
réutiliser dans une autre situation. Pour chaque tâche, définir avant
l'expérience les observations accessibles, la réussite, les références
et les conditions de transfert.

| Mesure | Unité ou définition |
|---|---|
| Réussite | Fraction de cas nouveaux réussis, pour une tâche et une distribution définies |
| Qualité des prédictions | Score probabiliste déclaré à l'avance, si le système produit des probabilités |
| Acquisition | Nombre d'interactions et coût de calcul nécessaires pour atteindre un seuil déclaré |
| Transfert | Résultat sur une nouvelle configuration, avec le budget d'adaptation explicitement indiqué |
| Rétention | Résultat sur des compétences antérieures, après de nouveaux apprentissages |
| Expérience reçue | Interactions, épisodes, contextes distincts et retours observés |
| Calcul dépensé | Mises à jour, temps de calcul actif, matériel et configuration |
| Durée réelle | Temps écoulé, y compris attente, actions et entrées/sorties |
| Taille du système | Paramètres stockés, degrés de liberté lorsque définis, mémoire persistante et état de calcul |

Le nombre d'unités créées et leur déplacement ne constituent pas, seuls,
une mesure de compétence. Si la représentation ou sa géométrie change,
les capacités restent évaluées sur des résultats observables définis.
Une différence de coordonnées ne doit pas devenir artificiellement un gain.

Un score vaut pour les tâches, informations et budgets annoncés.
Il n'est pas une unité universelle d'intelligence.

## Expérience et temps de calcul

Compter séparément les interactions avec l'environnement, les contextes
distincts rencontrés et les réutilisations de la mémoire. Dix mille mises
à jour sur dix observations ne sont pas dix mille nouvelles observations.
Dans un environnement bruité, répéter une observation peut apporter de
l'information statistique ; ce rôle doit être explicité.

Distinguer le temps de calcul actif du temps réel écoulé. Attendre ne
constitue pas une expérience d'apprentissage lorsque le système ne reçoit
aucune information et n'effectue aucune opération pertinente.

Les comparaisons présenteront deux vues : à expérience accessible comparable
et à coût de calcul comparable. Une même durée ne donne pas nécessairement
le même nombre d'essais à deux architectures.

## Fixer les horizons

Un pilote court sert à vérifier que l'expérience est informative, que
le mécanisme de mise à jour fonctionne et à mesurer son coût.
Il ne décide pas, à lui seul, de la valeur scientifique du mécanisme.

Avant l'expérience principale, enregistrer :

- La tâche, les distributions, les références et les graines.
- Le seuil de compétence et les critères de transfert/rétention.
- L'exposition minimale : interactions, diversité et retours accessibles.
- Plusieurs horizons d'apprentissage, espacés sur une plage large.
- Les budgets maximaux d'interactions, calcul, durée et mémoire.
- Les checkpoints et la règle d'arrêt ou de prolongation.

Les horizons de 100, 1 000 et 10 000 interactions sont désormais utilisés
pour la [première pièce](FIRST_PIECE.md). Ses horizons de validation sont
128, 1 024 et 4 096 nouvelles interactions. Ce choix est propre à cette
expérience. Les valeurs des autres mécanismes dépendront de la tâche
et du coût mesuré sur le matériel.
Il n'existe pas ici de durée supposée suffisante pour toute architecture.

Une prolongation motivée par une tendance encore positive doit être
annoncée avec son nouveau budget et ses critères. Les résultats
précédents restent visibles.

## Suivre des courbes

Enregistrer les performances à plusieurs checkpoints, en fonction des
interactions et du calcul dépensé. Observer le délai avant les premiers
gains, leur pente, les plateaux, les régressions, le transfert et l'oubli.

Répéter les essais avec plusieurs graines et plusieurs contextes.
Publier les dispersions et les incertitudes, avec les unités d'échantillonnage.
Une fluctuation sur quelques exemples ne suffit pas à établir une tendance.

Les observations réservées à l'évaluation ne doivent pas entraîner le modèle.
Les choix de paramètres et de checkpoints utilisent une validation séparée.
Conserver un test final indépendant. Tout apprentissage autorisé pendant
un test d'adaptation est explicitement compté dans son budget.

La sauvegarde doit permettre une reprise de l'état d'apprentissage complet.
Une prolongation poursuit cet état ; recréer un modèle avec les seuls
poids d'inférence ne constitue pas une reprise identique.

## Conclure à la bonne échelle

- **Gain observé :** amélioration reproductible pour les tâches et budgets testés.
- **Seuil non atteint dans le budget :** l'essai n'atteint pas l'objectif annoncé dans les conditions données ; cela ne démontre pas une incapacité pour toute durée.
- **Essai inexploitable :** défaut d'implémentation, information insuffisante, protocole modifié sans trace ou évaluation contaminée ; corriger avant une conclusion sur le mécanisme.

Un plateau constitue une observation sur une fenêtre donnée. Davantage
de temps peut changer le résultat ; le passage du temps ne garantit
pas une amélioration. La décision pratique peut rester de limiter
l'essai au budget disponible, en déclarant cette limite.

## Lecture des expériences précédentes

Les comparaisons V0/V1 à 200 interactions renseignent ce budget dans
un laboratoire de 32 couples état/action. Elles montrent notamment les
résultats des sélections active et aléatoire à cet horizon.
Elles ne démontrent pas leur classement pour toute durée, ni l'absence
possible de gains à un budget supérieur.

Les résultats historiques et leurs revues restent inchangés.
Ce protocole guide la [nouvelle conception](RESEARCH_RESET.md) et
est désormais appliqué dans le [rapport de la première pièce](FIRST_PIECE_LEARNING_RESULTS.md),
avec une courbe exécutée jusqu'à 10 000 interactions par tâche. Les V0/V1
n'ont pas été prolongées dans cette étape.

## Extension à l'ordre et aux changements cachés

Le [protocole temporel](FIRST_PIECE_TEMPORAL.md) reprend les horizons
100, 1 000 et 10 000 avant et après un changement, dans le même contexte.
Les [résultats](FIRST_PIECE_TEMPORAL_RESULTS.md) distinguent l'inversion
des sorties du remplacement de la relation utilisée.

Le délai de récupération est la première mesure, à intervalle de
256 interactions, atteignant succès >=0.95 et Brier <=0.02 sur 128
épisodes indépendants. Les évaluations correspondantes sont comptées
séparément des retours qui entraînent le modèle. Cette sonde ne donne
pas un instant exact de récupération.

La moyenne de gain conditionnel sur un bloc de validation peut être
bornée sans affirmer la stabilité future d'une règle qui change.
Les mesures indépendantes des régimes fixes donnent cette performance.
Les essais arrêtés pour futilité restent des essais consommés, sans
conclusion générale d'impossibilité.
