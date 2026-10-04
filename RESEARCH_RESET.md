# Nouvelle conception de Setharkk

## Point de départ

La conception repart des exigences de l'utilisateur et d'une hypothèse
à construire. La V0 et la V1 restent des références expérimentales :
leurs choix d'architecture ne définissent pas la nouvelle conception.

Le premier travail porte sur un mécanisme d'apprentissage précis.
Aucune nouvelle architecture n'est encore implémentée dans ce document.

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

Le sens opérationnel de « réseau non euclidien » devra être précisé pour
la nouvelle construction. Une géométrie émergente devra être définie et
mesurée. L'absence d'une géométrie définie ne suffit pas à satisfaire cette
exigence.

## Choix ouverts

L'hyperboloïde H4, la courbure -1, les huit neurones à prototypes,
l'ensemble de trois prédicteurs et l'optimiseur V1 sont des choix des
expériences précédentes. La nouvelle conception peut remettre ces choix
en question.

Les unités de calcul, les variables de l'état interne, les relations,
la géométrie et les règles de modification restent à définir.
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

Cette proposition est un point de travail. Elle ne fixe pas encore une
règle de mise à jour et ne constitue pas une innovation démontrée.

Une divergence de résultats peut venir du hasard ou d'une information
inaccessible. La règle doit traiter ces cas ; elle ne doit pas créer
automatiquement une distinction pour chaque erreur.

## Première pièce à définir

Le mécanisme devra répondre concrètement à cinq questions :

1. Quel est son état interne, et comment représente-t-il l'historique ?
2. Que prédit-il, et quel retour observable permet d'évaluer cette prédiction ?
3. Qu'est-ce qui se modifie durablement lors d'un apprentissage ?
4. Quelle règle crée, fusionne ou supprime une distinction, sous quel budget ?
5. Comment cette modification est-elle conservée et réutilisée ?

La règle doit être assez précise pour calculer une mise à jour sur un petit
exemple avant de construire le dialogue et la coordination d'agents.
Le code devra enregistrer les changements effectifs et l'état nécessaire
à la reprise.

## Première expérience proposée

Un petit environnement séquentiel présenterait des observations identiques
dans des contextes différents, dont certains peuvent être distingués par
l'historique. Un contrôle présenterait des différences purement aléatoires.

Les critères seraient la prédiction sur de nouvelles séquences, le transfert,
l'oubli des compétences antérieures, le coût des distinctions créées et
l'équivalence entre une exécution continue et une exécution reprise.

Les références de comparaison recevraient les mêmes informations et un
budget comparable. Cette expérience teste un mécanisme ; elle ne démontre
pas à elle seule une intelligence générale ou une originalité scientifique.

## Méthode de recherche

Formuler une hypothèse et sa règle, examiner ses antécédents, puis
construire une expérience qui peut la confirmer ou la réfuter.
La littérature aide à situer une idée formulée ; elle ne fixe pas à
l'avance les seuls mécanismes que l'on peut proposer.

Les décisions d'architecture viendront des hypothèses retenues et des
résultats. Les résultats et revues de la V0/V1 restent accessibles pour
éviter de confondre nouvelle conception et progrès déjà démontré.
