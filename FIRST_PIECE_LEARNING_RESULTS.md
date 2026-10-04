# Première pièce : apprentissage mesuré et résolution des limites

Un apprenant est maintenant implémenté. Il reçoit les événements un à un,
modifie ses prototypes neuronaux sur S² et teste une distinction contre
un contrôle ajusté à budget égal. Dans le laboratoire structuré, les cinq
essais passent du niveau du hasard à 100 % des cas d'évaluation observés.

- Source vérifiée : [0c63e0e](https://github.com/Setharkk/Remake-setharkk/commit/0c63e0e8a090c500184bd421f961ff38c888594c).
- Exécution : [Actions 37202478630](https://github.com/Setharkk/Remake-setharkk/actions/runs/37202478630).
- **35 tests réussis sous Windows et Linux**, Python 3.11, bibliothèque standard.
- Cinq graines : 0, 1, 2, 3, 4.
- [Définition, formules et taille du mécanisme](FIRST_PIECE.md).

## Les limites de la revue et leur résolution

| Limite précédente | Construction et vérification actuelles |
|---|---|
| Aucun mécanisme n'apprenait les distinctions | Une proposition est sélectionnée depuis les résultats passés ; ses prototypes sont entraînés et ses prédictions validées sur de nouvelles interactions |
| Gain attribué à une distinction sans retrait contrôlé | Candidat et contrôle ont les mêmes prototypes, initialisation, observations, labels et nombre de mises à jour ; la version sans distinction utilise le contrôle ajusté |
| Historique fourni en bloc | L'interface fournit un événement à la fois ; la mémoire temporaire doit conserver le signal jusqu'à l'action |
| Géométrie du nouveau réseau indéfinie | Tous les paramètres neuronaux appris sont des points de S², avec lecture géodésique et mises à jour exponentielles riemanniennes |
| Reprise et rétention de l'apprenant non évaluées | Reprise JSON exacte testée pendant une validation avec épisode en cours ; la tâche antérieure est réévaluée après une deuxième tâche |

Les trois familles de défauts de code corrigées dans la première revue
restent couvertes : deux queues statistiques, cas numériques extrêmes
et sauvegarde des horizons de l'audit.

## Protocole et unités

Les horizons d'apprentissage sont **100, 1 000 et 10 000 interactions**.
Une interaction inclut l'arrivée de plusieurs événements, une action et
un résultat. Le nombre d'événements n'est donc pas identique au nombre
d'interactions.

Les cinq graines sont exécutées dans trois mondes : structuré, aléatoire
et action seule. Cela représente 15 conditions et 150 000 interactions
initiales. Les cinq conditions structurées reçoivent ensuite une deuxième
tâche de 10 000 interactions : **200 000 interactions d'apprentissage par
système d'exploitation**.

Les deux apprenants reçoivent les mêmes événements, actions et résultats.
Chaque version effectue au total **210 220 mises à jour neuronales**, en
comptant les ajustements du candidat et du contrôle. Ce nombre dépasse
l'exposition parce que les 256 premiers enregistrements sont réutilisés
pour ajuster les deux modèles. Ce ne sont pas des observations nouvelles.

L'égalité du budget de mises à jour est vérifiée par le programme.
Elle ne démontre pas un temps CPU exactement égal : le coût de routage,
des branches de contrôle et des sauvegardes peut différer.

Chaque horizon de la tâche initiale est évalué sur 256 épisodes nouveaux.
Chaque évaluation de transfert ou de rétention utilise 1 024 épisodes.
Le programme génère **26 880 épisodes d'évaluation par système** et
simule trois décisions de politique par épisode, soit 80 640 actions
supplémentaires dans des copies du monde.

Les prédictions probabilistes utilisent une action aléatoire commune.
La réussite de politique mesure le résultat de l'action ayant la
probabilité de réussite maximale. Les évaluations utilisent des clones
et ne mettent pas à jour les poids ou compteurs d'apprentissage.

Le temps écoulé enregistré comprend apprentissage, simulation, évaluation
et entrées/sorties. Il n'est pas un chronométrage isolé de l'optimiseur.

## Courbe observée dans le monde structuré

Moyennes des cinq graines. La réussite vaut pour les 256 nouveaux épisodes
par graine à chaque horizon.

| Interactions d'apprentissage | Version complète | Sans distinction | Avec mémoire effacée |
|---:|---:|---:|---:|
| 100 | 50.94 % | 50.94 % | 50.94 % |
| 1 000 | 47.58 % | 47.58 % | 47.58 % |
| 10 000 | 100 % | 49.84 % | 49.45 % |

À 10 000 interactions, la version complète réussit les **1 280 épisodes
nouveaux observés** dans le monde structuré. Le Brier moyen est
0.000001205, contre 0.258577 sans distinction.

Les faibles performances à 100 et 1 000 interactions ne permettaient
donc pas de conclure à une absence d'apprentissage dans le budget plus long.

Dans les dix tâches structurées, le symbole proposé est 0. La distinction
est admise à **1 280 interactions par tâche** : 256 pour l'ajustement,
puis 1 024 nouvelles pour la validation. Elle reste en attente au premier
horizon de validation de 128 exemples. Les cinq graines couvrent les
deux règles contraires : le symbole n'est pas à lui seul la bonne action.

Le candidat et le contrôle effectuent chacun exactement 256 mises à jour
avant d'être figés. Après admission, les nouveaux retours continuent
de déplacer les neurones du modèle retenu.

## Transfert et rétention

Moyennes des cinq graines, 1 024 nouveaux épisodes par graine et par ligne.

| Évaluation | Version complète | Sans distinction | Avec mémoire effacée |
|---|---:|---:|---:|
| Historiques plus longs avant l'autre tâche | 100 % | 50.43 % | 49.39 % |
| Première tâche après l'apprentissage de l'autre | 100 % | 49.92 % | 49.92 % |
| Nouvelle tâche sur des historiques plus longs | 100 % | 50.49 % | 50.66 % |

Le transfert conserve la même règle et change les distracteurs et délais.
Il n'établit pas une généralisation à des règles jamais représentées
par la famille de propositions.

Les deux tâches ont des identifiants explicites et des réseaux séparés.
La rétention vérifie cette protection modulaire, pas encore l'absence
d'oubli dans un réseau dont tous les neurones sont partagés.

Le contrôle sans mémoire conserve les poids de la version complète,
mais efface son état avant chaque événement et avant la surface.
Sa chute de performance montre le rôle du signal conservé dans cet essai ;
ce contrôle n'est pas réentraîné pour compenser l'effacement.

## Bruit et relation dépendant de l'action seule

À 10 000 interactions :

| Monde | Distinctions admises | Réussite moyenne | Brier moyen |
|---|---:|---:|---:|
| Résultats aléatoires | 0 sur 5 | 49.84 % | 0.258784 |
| Résultat déterminé par l'action seule | 0 sur 5 | 100 % | 0.000001059 |

Les propositions atteignent le statut **inconclusive**, pas « rejetée
avec certitude ». Aucune distinction n'est conservée dans ces budgets.
Cela n'établit pas un risque nul d'admission dans tous les mondes possibles.

Dans le bruit, le prédicteur constant p = 0.5 a un Brier de 0.25 :
le réseau est donc légèrement moins bon que ce contrôle simple.
Le bruit n'est pas une réussite prédictive ; le résultat utile ici est
l'absence de distinction admise dans les essais exécutés.

Le monde action seule montre qu'une compétence prédictive peut être
acquise sans créer une distinction temporelle. Cela répond au cas de
recalibration soulevé dans la revue, dans cette architecture et ce protocole.

## Géométrie et reprise

Les tests contrôlent la norme des paramètres, la tangence des mises à jour,
l'amélioration d'un score après une mise à jour et l'équivalence sous
rotation simultanée des neurones et des repères de sortie.

Un apprenant et son monde sont sauvegardés en JSON pendant une validation,
après quelques événements d'un épisode. Après restauration, **64
interactions supplémentaires** produisent les mêmes événements,
prédictions, résultats et état final. Un autre test couvre 32 interactions
dans un transfert. Les états aléatoires, modèles figés, buffers,
compteurs et mémoire en cours sont conservés.

Les checkpoints incohérents sont rejetés : coordonnées hors sphère ou
non représentables, identifiant de tâche booléen, modèles figés dans une
phase incompatible et budgets de validation incohérents.

La reprise exacte est testée séparément à l'intérieur de chaque système.
La comparaison entre Windows et Linux exclut le temps écoulé : les
décisions, structures et réussites sont les mêmes. Sur 4 241 valeurs
numériques, l'écart absolu maximum est **9.33e-15**, sous la tolérance
déclarée de 1e-10. Il ne s'agit pas d'une identité binaire entre systèmes.

## Taille et limites restantes

Deux tâches actives utilisent **huit prototypes appris**, soit
**24 coordonnées et 16 degrés de liberté intrinsèques**.
Les candidats et contrôles temporaires, masques, compteurs, buffers de
validation et générateurs aléatoires augmentent l'état stocké.
Les degrés de liberté ne représentent donc pas toute la consommation mémoire.

Les contraintes restent explicites :

- Une proposition de présence de symbole par tâche ; une seule tentative.
- Dix symboles possibles et deux tâches par défaut.
- Une géométrie sphérique fixe ; aucun avantage sur une version euclidienne
  n'a encore été mesuré.
- La sélection structurelle utilise des statistiques de retours observés.
  Elle ne constitue pas un réseau récurrent profond entièrement différentiable.
- Les snapshots permettent de restaurer l'apprenant et le monde ;
  l'expérience n'offre pas encore une commande de prolongation automatique.
- Les tâches sont synthétiques. Dialogue, choix autonome de buts, agents
  et actions sur le PC restent hors de cette première pièce.

Le résultat est un mécanisme de première pièce fonctionnel et borné,
pas une preuve d'intelligence générale ou de nouveauté scientifique.

## Résultats conservés

- [Mesures Windows](first_piece_learning_results/run_37202478630/windows.json).
- [Mesures Linux](first_piece_learning_results/run_37202478630/linux.json).
- [Agrégats et comparaison des systèmes](first_piece_learning_results/run_37202478630/aggregate.json).
- Les archives first-piece-learning de l'exécution contiennent les états
  complets des deux apprenants, du monde et du générateur des actions.
  Elles ont une durée de conservation limitée.
- La [validation initiale](FIRST_PIECE_VALIDATION.md) et la
  [revue initiale](CODE_REVIEW_FIRST_PIECE.md) restent des résultats historiques.

Pour reproduire :

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.learning_run --seeds 0 1 2 3 4 --out first_piece/lab_runs/apprentissage_2
~~~

Python 3.11, sans dépendance supplémentaire. Le chemin de sortie doit être neuf.
