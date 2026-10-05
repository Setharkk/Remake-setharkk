# Remake Setharkk

Projet de recherche pour un cortex neuronal courbe qui apprend des
conséquences de ses actions et choisit des expériences.

Le cœur courant utilise le format 8. Le [service coopératif](FIRST_PIECE_COOPERATIVE.md)
permet de suspendre et reprendre le calcul par quotas et expose la couverture
par action. Le [protocole gelé](FIRST_PIECE_READINESS_PROTOCOL.md) et les
[résultats](FIRST_PIECE_READINESS_RESULTS.md) séparent sa validation d'ingénierie
de l'expérience de représentation adaptative des répétitions.

Les [corrections prioritaires](PRIORITY_FIXES.md)
publient les défauts corrigés, les tests Windows/Linux, la compatibilité
et les mesures CPU avant/après. Le [rapport du format 7](PLASTIC_REVISION_RESULTS.md)
conserve les expériences à 64 symboles et 16 contextes. Les rapports suivants
documentent les étapes précédentes et leurs périmètres respectifs.

La [revue du code de format 7](CODE_REVIEW_PLASTIC.md) publie les défauts reproduits, les profils CPU et les écarts à la spécification. Ses quatre défauts sont corrigés dans le format 8 ; les profils historiques restent disponibles.

La [première pièce](FIRST_PIECE.md) contient maintenant un apprenant :
mémoire alimentée événement par événement, prototypes neuronaux sur S²
et distinction proposée depuis les résultats de ses actions. Un contrôle
sans distinction reçoit les mêmes expériences et le même budget de mises à jour.

Les [résultats mesurés](FIRST_PIECE_LEARNING_RESULTS.md) publient les 35 tests
Windows/Linux, les courbes à 100, 1 000 et 10 000 interactions, le transfert,
la rétention et la reprise JSON exacte. Ces résultats décrivent la référence de présence,
limitée à un symbole par tâche dans les tâches synthétiques décrites.

L'[architecture commune](SYSTEM_ARCHITECTURE.md) définit les observations,
prédictions, propositions d'agents et résultats d'actions versionnés.
La première pièce expose cet adaptateur sans partager ses détails neuronaux.
La [validation d'intégration](SYSTEM_INTEGRATION_VALIDATION.md) publie
51 tests Windows/Linux et la parité avec l'apprenant direct.
La [première pièce révisable](FIRST_PIECE_TEMPORAL.md) ajoute une mémoire
de premier ordre d'apparition, des tentatives bornées et le remplacement
d'une relation dans le même contexte. Elle conserve les contrats communs
et le réseau neuronal sur S². Les
[résultats temporels](FIRST_PIECE_TEMPORAL_RESULTS.md) publient les mesures
et les limites de cette révision.

La [version partagée](FIRST_PIECE_SCALE.md) travaille maintenant la montée
à l’échelle : vocabulaire opaque, plusieurs actions, combinaisons de relations
et mêmes poids sphériques entre les contextes. Le
[rapport de montée à l’échelle](FIRST_PIECE_SCALE_RESULTS.md) publie les
essais jusqu’à 64 symboles et 16 contextes, les coûts et les limites.
Elle reste synthétique ; son budget de mémoire et de recherche est explicite.

La [revue du code précédent](CODE_REVIEW_CURRENT.md) conserve les six familles de défauts reproduites. Les [corrections vérifiées](CURRENT_FIXES.md) sont maintenant livrées avec **97 tests Windows/Linux**, une comparaison avant/après, un cycle de vie borné de validation et une migration explicite des checkpoints partagés vers le format 2. Ce rapport décrit le moteur historique à budget fini.

Le [mode renouvelable](RENEWABLE_SEARCH.md) ajoute maintenant un budget statistique sommable et un journal borné, avec **104 tests Windows/Linux**. Les [expériences longues](RENEWABLE_SEARCH_RESULTS.md) démontrent l’apprentissage après épuisement du mode fini, mais aussi deux échecs : oubli sous bruit et admission bloquée des changements minoritaires. Le [mode consolidé](CONSOLIDATION.md) corrige maintenant ces deux échecs dans le protocole testé, avec **113 tests Windows/Linux**. Les [mesures complètes](CONSOLIDATION_RESULTS.md) montrent une compétence conservée à 100 % après 80 000 retours bruités et six changements successifs admis, sur trois graines. La mémoire protégée ajoute 32 points S² pour quatre actions. Elle augmente toutefois la surconfiance sous bruit ; une première admission est aussi plus lente. Ces coûts et limites sont publiés.

Le [mode calibré](CALIBRATION.md) conserve le réseau et les décisions de compétence du mode consolidé, puis ajuste ses probabilités depuis les résultats récents des actions exécutées. Le [protocole](CALIBRATION_PROTOCOL.md) sépare la conservation de la règle des scores probabilistes ; le [rapport](CALIBRATION_RESULTS.md) publie les mesures, les coûts et les limites.

La [nouvelle base de recherche](RESEARCH_RESET.md) conserve les exigences
du projet. Le [protocole de mesure](MEASUREMENT_PROTOCOL.md) fixe les unités
et la portée des conclusions.
La [validation initiale](FIRST_PIECE_VALIDATION.md) et la
[revue initiale](CODE_REVIEW_FIRST_PIECE.md) conservent les preuves du
laboratoire avant cet apprenant.

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

La [révision plastique sur S²](PLASTIC_REVISION.md), de format 8, conserve
les contrats de la première pièce et les imports explicites. Le
[rapport](PLASTIC_REVISION_RESULTS.md) publie 139 tests Windows/Linux,
les délais, les ablations et la montée à 64 symboles/16 contextes.
Le pire délai testé sur les trois graines initiales passe de 21 000 à
10 000 retours ; l'avantage propre du transfert de poids reste non établi.


Le [moteur de trace S² v2](FIRST_PIECE_TRACE_V2.md) ajoute une lecture calibrée,
une révision prospective des poids protégés et un service coopératif optionnel.
Le [protocole](FIRST_PIECE_TRACE_V2_PROTOCOL.md) fixe les budgets de mesure ;
le [rapport](FIRST_PIECE_TRACE_V2_RESULTS.md) publie les résultats et les limites.
Le moteur format 8 reste le défaut ; les capacités des deux backends sont explicites.
