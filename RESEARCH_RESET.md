# Nouvelle conception de Setharkk

## Point de départ

La conception repart des exigences de l'utilisateur et d'une hypothèse
à construire. La V0 et la V1 restent des références expérimentales :
leurs choix d'architecture ne définissent pas la nouvelle conception.

Le premier travail porte sur un mécanisme d'apprentissage précis.
La [première pièce](FIRST_PIECE.md) implémente maintenant un mécanisme
borné : mémoire d'événements, neurones sphériques et proposition d'une
distinction testée contre un contrôle ajusté. Le
[rapport d'apprentissage](FIRST_PIECE_LEARNING_RESULTS.md) conserve ses
résultats, ses contrôles et la reprise de son état complet.

## Exigences conservées

- Apprendre des conséquences observées de ses actions pendant l'interaction.
- Conserver les compétences acquises et reprendre son apprentissage après un arrêt.
- Progresser selon les demandes de l'utilisateur et pouvoir choisir des objectifs propres.
- Un cortex commun coordonnant des agents comme extensions de lui-même.
- À terme, dialoguer et agir sur les fichiers et applications du PC.
- Un petit budget de paramètres et de mémoire, mesuré explicitement.
- Définir un réseau lui-même non euclidien, conformément à l'exigence formulée.

Le matériel indiqué est Windows, NVIDIA RTX avec 12 Go de VRAM et 64 Go
de RAM. Ces ressources servent de contrainte expérimentale ; elles ne
constituent pas une validation de l'architecture à venir.

La première pièce définit « réseau non euclidien » par des paramètres
neuronaux sur S², des distances géodésiques et des mises à jour exponentielles.
Ce choix est expérimental et sa supériorité reste à mesurer. Une géométrie émergente devra être définie et
mesurée. L'absence d'une géométrie définie ne suffit pas à satisfaire cette
exigence.

## Choix ouverts

L'hyperboloïde H4, la courbure -1, les huit neurones à prototypes,
l'ensemble de trois prédicteurs et l'optimiseur V1 sont des choix des
expériences précédentes. La nouvelle conception peut remettre ces choix
en question.

La première pièce précise ses unités, états, géométrie et mises à jour.
Les mécanismes plus généraux, la fusion et la suppression des distinctions
restent à définir.
La mécanique des fluides est une source possible de mécanismes ;
elle n'est pas choisie comme fondement par défaut.

## Hypothèse candidate discutée

Un système pourrait apprendre à créer, fusionner et supprimer les
distinctions internes avec lesquelles il prédit les conséquences de ses
actions, sous un budget limité.

Exemple : deux situations regroupées dans une même représentation donnent
des conséquences systématiquement différentes. Le système recherche dans
les observations et leur historique une distinction qui explique cette
différence, puis teste si elle aide sur de nouvelles expériences.

La première pièce met en œuvre une forme limitée de cette hypothèse :
proposer et conserver une présence de symbole par tâche. Les règles sont
précisées dans sa définition ; aucune innovation scientifique n'est démontrée.

Une divergence de résultats peut venir du hasard ou d'une information
inaccessible. La règle doit traiter ces cas ; elle ne doit pas créer
automatiquement une distinction pour chaque erreur.

## Questions qui guident la première pièce

La première pièce répond de façon bornée à ces cinq questions :

1. Quel est son état interne, et comment représente-t-il l'historique ?
2. Que prédit-il, et quel retour observable permet d'évaluer cette prédiction ?
3. Qu'est-ce qui se modifie durablement lors d'un apprentissage ?
4. Quelle règle crée, fusionne ou supprime une distinction, sous quel budget ?
5. Comment cette modification est-elle conservée et réutilisée ?

La règle doit être assez précise pour calculer une mise à jour sur un petit
exemple avant de construire le dialogue et la coordination d'agents.
Le code conserve désormais ses paramètres, compteurs, états de validation
et mémoire en cours dans un checkpoint complet.

## Première expérience proposée

Un petit environnement séquentiel présenterait des observations identiques
dans des contextes différents, dont certains peuvent être distingués par
l'historique. Un contrôle présenterait des différences purement aléatoires.

L'objectif initial retenu est de découvrir une règle inconnue puis de la
réutiliser dans une autre situation. La durée d'exposition et l'unité de
mesure font partie du protocole, conformément à la précision de l'utilisateur.

Les critères seraient la prédiction sur de nouvelles séquences, le transfert,
l'oubli des compétences antérieures, le coût des distinctions créées et
l'équivalence entre une exécution continue et une exécution reprise.

Les références de comparaison recevraient les mêmes informations et un
budget comparable. Cette expérience teste un mécanisme ; elle ne démontre
pas à elle seule une intelligence générale ou une originalité scientifique.

Le [protocole de mesure et de durée](MEASUREMENT_PROTOCOL.md) distingue
les expériences reçues, le coût de calcul et les compétences observées.
Il demande des courbes sur plusieurs horizons et des conclusions limitées
aux budgets effectivement testés.

## Méthode de recherche

Formuler une hypothèse et sa règle, examiner ses antécédents, puis
construire une expérience qui peut la confirmer ou la réfuter.
La littérature aide à situer une idée formulée ; elle ne fixe pas à
l'avance les seuls mécanismes que l'on peut proposer.

Les décisions d'architecture viendront des hypothèses retenues et des
résultats. Les résultats et revues de la V0/V1 restent accessibles pour
éviter de confondre nouvelle conception et progrès déjà démontré.
