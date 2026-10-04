# Exigences du projet Setharkk

Ces exigences reprennent les demandes de l'utilisateur. La correction
essentielle est que le réseau lui-même doit être non euclidien.

La [nouvelle conception](RESEARCH_RESET.md) reprend ces exigences. Les choix
mathématiques de la référence V1 restent décrits ci-dessous ;
la première pièce adopte maintenant une construction sphérique distincte.

## Première pièce de présence, référence

La [première pièce](FIRST_PIECE.md) utilise un petit réseau à prototypes
sur S². Tous ses paramètres neuronaux appris sont des points sphériques ;
la lecture utilise des distances géodésiques et les mises à jour des
applications exponentielles de gradients tangents.

Deux tâches utilisent huit points appris, vingt-quatre coordonnées et
seize degrés de liberté intrinsèques actifs. Les modèles temporaires et
les états non neuronaux sont comptés séparément dans sa définition.

Elle reçoit les événements un par un et peut conserver une distinction
de présence de symbole sous un budget fixé. Le
[rapport mesuré](FIRST_PIECE_LEARNING_RESULTS.md) publie 35 tests
Windows/Linux, le contrôle sans distinction, le transfert, la rétention
par tâches séparées et la reprise complète du monde et de l'apprenant.

Sa géométrie et ses opérations sont vérifiables ; sa supériorité sur une
version euclidienne ou son originalité ne sont pas démontrées.

## Cohérence entre les pièces

L'[architecture commune](SYSTEM_ARCHITECTURE.md) définit des messages JSON
versionnés pour les observations, prédictions, propositions et résultats.
La première pièce possède un adaptateur avec une seule autorité
d'apprentissage. Des agents simulés peuvent contribuer au même modèle ;
les objectifs, l'essaim autonome et l'exécuteur PC restent à développer.

Les contraintes du laboratoire sont annoncées par ses capacités, sans
imposer les numéros de tâches et actions binaires aux interfaces globales.
Le [protocole temporel suivant](FIRST_PIECE_NEXT_PROTOCOL.md) demande
d'apprendre l'ordre puis de remplacer une règle sans nouveau contexte.
La [révision temporelle](FIRST_PIECE_TEMPORAL.md) implémente une famille
bornée de premiers ordres d'apparition, des tentatives révisables et le
remplacement d'une relation dans le même contexte. Les
[résultats temporels](FIRST_PIECE_TEMPORAL_RESULTS.md) en donnent la portée.

## Première pièce partagée et montée à l’échelle

La [version partagée](FIRST_PIECE_SCALE.md) garde les neurones sur S²,
les distances géodésiques et les mises à jour exponentielles. Elle reçoit des
symboles opaques, expose de deux à seize actions et partage la même banque
entre les contextes. Elle cherche des combinaisons d’au plus trois prédicats.
Le [rapport](FIRST_PIECE_SCALE_RESULTS.md) distingue les capacités
configurables des échelles réellement testées.

Quatre actions et huit routes allouent 64 points S² en service, contrôle
de même capacité compris, soit 128 degrés de liberté intrinsèques. Ce budget
ne croît pas en passant de huit à seize contextes ; la mémoire discrète,
elle, augmente avec le nombre de contextes sous une borne configurée.
L’essai à deux actions possède la moitié de cette capacité.

La bibliothèque de prédicats, les frontières d’épisode et l’exploration
uniforme sont fournies. La continuité du programme admis est un biais
explicite, pas une preuve de découverte d’une logique entièrement nouvelle.

## Exigence géométrique de la référence V1

La V1 donne un sens vérifiable à cette exigence :

1. Chaque paramètre neuronal appris est un point de H4, de courbure -1.
   Sa représentation Lorentz possède cinq coordonnées avec <p,p>_L=-1
   et p0>0. Aucune matrice linéaire euclidienne apprise n'est utilisée
   dans le cœur de ce réseau.
2. Les neurones à prototypes interagissent par des distances géodésiques.
   Les représentations intermédiaires restent sur H4.
3. Les agrégations sont des centroïdes de Lorentz. Leur objectif est la
   somme des cosh des distances pondérées, pas la somme des distances carrées.
4. Les gradients sont convertis avec la métrique de Lorentz et projetés
   dans les espaces tangents. Les mises à jour utilisent l'application
   exponentielle ; les premiers moments sont transportés parallèlement.
5. Des tests contrôlent les contraintes des paramètres après apprentissage,
   la tangence des moments, l'invariance du réseau par isométrie et
   l'équivalence des mises à jour par isométrie lorsque la borne radiale
   de stabilité est inactive.

Non euclidien qualifie ici la géométrie des paramètres et des opérations
du réseau. Les coordonnées stockées, probabilités, coefficients d'activation
et pertes restent des nombres réels. Les espaces tangents sont linéaires
par définition ; cela ne rend pas euclidiens les paramètres qu'ils déplacent.

## Exigences fonctionnelles et état

| Exigence | État |
|---|---|
| Réseau lui-même non euclidien | Version partagée sur S², 85 tests Windows/Linux ; références temporelle, de présence et V1 sur H4 conservées |
| Apprendre des résultats de ses actions pendant une interaction | Implémenté dans la première pièce séquentielle et dans la référence de fichiers |
| Apprentissage continu avec reprise complète | État partagé restaurable, y compris requête en attente ; 16 essais globaux par défaut, puis poursuite des gradients sans nouvelle recherche |
| Objectifs proposés par l'utilisateur et objectifs choisis par le système | À développer |
| Cortex avec un essaim d'agents comme extensions de lui-même | À développer |
| Dialogue | À développer |
| Agir sur des applications du PC | À développer |
| Petit budget de paramètres | Version partagée : 128 degrés de liberté en service pour quatre actions, contrôle inclus ; 256 pendant une validation ; 64/128 pour deux actions ; références conservées |

La V1 contient 34 points par modèle : 6 prototypes de bits d'observation,
4 d'action, 8 clés de neurones, 8 valeurs de neurones et 8 prototypes de
sortie. Cela représente 170 coordonnées stockées, mais 136 degrés de liberté
intrinsèques par modèle. Les trois modèles représentent 510 coordonnées
et 408 degrés de liberté. Ils constituent un ensemble de prédicteurs,
pas un essaim d'agents.

La V0 reste archivée comme référence expérimentale. Ses poids étaient
euclidiens ; ses résultats ne décrivent pas l'architecture V1.

## Choix expérimentaux

La courbure -1, la dimension 4, les huit neurones à prototypes, les
températures et les réglages d'optimisation sont des choix explicites de
prototype. Ils ne constituent pas une théorie du cortex autonome et ne
sont pas présentés comme des réglages optimaux.

Cette architecture utilise des mécanismes géométriques connus. Aucune
innovation scientifique ou supériorité de performance n'est revendiquée
sans comparaison appropriée.
