# Remake Setharkk

Projet de recherche pour un cortex neuronal courbe qui apprend des
conséquences de ses actions et choisit des expériences.

La conception repart d'une [nouvelle base de recherche](RESEARCH_RESET.md),
avec les exigences de l'utilisateur et un mécanisme d'apprentissage à définir.
Le [protocole de mesure](MEASUREMENT_PROTOCOL.md) précise les unités,
les horizons d'apprentissage et les limites des conclusions.
La [première pièce](FIRST_PIECE.md) définit une mémoire qui apprend à distinguer
et prépare son [laboratoire séquentiel](first_piece/README.md).

[Cortex Lab V1](cortex_lab_v1/README.md) reste une référence expérimentale.
Tous ses paramètres neuronaux sont des points hyperboliques appris avec un
optimiseur riemannien. La [spécification](SPEC.md) formalise cette exigence et indique
les capacités restant à construire. La [validation de la V1](INTRINSIC_VALIDATION.md)
publie les tests Windows/Linux et les limites de son apprentissage.
La [revue de la V1](CODE_REVIEW_V1.md) expose les défauts reproduits et les
corrections proposées. La [note sur les travaux antérieurs](LITERATURE_NON_EUCLIDEAN.md)
situe cette architecture dans la littérature.

La première expérience de référence est [Cortex Lab V0](cortex_lab_v0/README.md) : un laboratoire
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

La [deuxième revue](CODE_REVIEW_2.md) corrige les instantanés de poids,
l'initialisation aléatoire et les métriques lors d'une interruption.
Ses 21 tests et la comparaison complète passent sur Windows et Linux.

Le [benchmark sur 20 graines](BENCHMARK_RESULTS_20_SEEDS.md) publie les
courbes, les comparaisons et les échecs. L'apprentissage progresse dans ce
laboratoire, mais la sélection active reste moins efficace en moyenne que
le hasard et plusieurs conditions régressent après 100 expériences.
