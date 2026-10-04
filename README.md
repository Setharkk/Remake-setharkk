# Remake Setharkk

Projet de recherche pour un cortex neuronal courbe qui apprend des
conséquences de ses actions et choisit des expériences.

La première pièce est [Cortex Lab V0](cortex_lab_v0/README.md) : un laboratoire
de fichiers avec 72 paramètres par modèle et trois modèles pour estimer
l'incertitude. Il compare les transitions hyperboliques et euclidiennes,
ainsi que l'exploration active et aléatoire.

Les buts à long terme sont le dialogue, une mémoire commune et des agents
coordonnés pour progresser selon les demandes de l'utilisateur et leurs
propres objectifs. Le laboratoire actuel sert à mesurer un mécanisme
d'apprentissage limité ; ces capacités générales restent à développer.

Les instructions Windows, les formules, le protocole d'évaluation et les
limites se trouvent dans le README du laboratoire.

Le [premier essai mesuré](EXPERIMENT_RESULTS.md) conserve les résultats de
la comparaison exécutée sous Windows et Linux, ainsi que ses limites.

La [révision du code](CODE_REVIEW.md) détaille les défauts corrigés, les
17 tests réussis sur Windows et Linux et les mesures du protocole version 2.

La [deuxième revue](CODE_REVIEW_2.md) vérifie les instantanés de poids,
l'initialisation aléatoire et les métriques lors d'une interruption.
