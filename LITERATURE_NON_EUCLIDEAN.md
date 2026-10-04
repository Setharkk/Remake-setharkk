# Réseaux non euclidiens : travaux antérieurs et position de la V1

Oui : des réseaux neuronaux dont les représentations et les opérations
utilisent une géométrie non euclidienne existent déjà dans la littérature.
Les réseaux hyperboliques en constituent une famille publiée au moins
depuis 2018. Le mot « non euclidien » ne désigne pas une seule architecture.

Cette note répond à cette question avec trois exemples vérifiés dans les
dépôts officiels des auteurs le 4 octobre 2026. Il ne s'agit pas d'une revue
exhaustive des publications, ni d'une recherche établissant l'originalité
de notre architecture particulière.

## Exemples vérifiés

| Travail | Date | Apport pertinent |
|---|---|---|
| Ganea, Bécigneul et Hofmann, Hyperbolic Neural Networks | NeurIPS 2018 | Couches et réseaux récurrents hyperboliques fondés sur la géométrie de la boule de Poincaré et les opérations de Möbius |
| Shimizu, Mukuta et Harada, Hyperbolic Neural Networks++ | ICLR 2021 | Développement de couches hyperboliques ; le dépôt officiel fournit notamment une application à la traduction |
| Chen et collaborateurs, Fully Hyperbolic Neural Networks | Prépublication 2021 | Couches fondées sur le modèle de Lorentz ; exemples de graphes de connaissances, embeddings de réseaux et traduction |

Sources :

1. [Hyperbolic Neural Networks — publication](https://arxiv.org/abs/1805.09112)
   et [code des auteurs](https://github.com/dalab/hyperbolic_nn).
   Le README cite NeurIPS 2018 et fournit une configuration avec GRU,
   couche entièrement connectée et classification hyperboliques.
2. [Hyperbolic Neural Networks++ — publication ICLR](https://openreview.net/forum?id=Ec85b0tUwbA)
   et [implémentation officielle](https://github.com/mil-tokyo/hyperbolic_nn_plusplus).
   Le README identifie explicitement l'acceptation à ICLR 2021.
3. [Fully Hyperbolic Neural Networks — publication](https://arxiv.org/abs/2105.14686)
   et [code des auteurs](https://github.com/chenweize1998/fully-hyperbolic-nn).
   Le README cite la prépublication de 2021 et décrit les trois applications.

## Une nuance nécessaire sur les paramètres

Un réseau qualifié d'hyperbolique peut avoir des états et des couches
hyperboliques tout en utilisant des matrices numériques libres pour
paramétrer certaines transformations.

Exemple vérifié : [LorentzLinear dans le code de Chen et collaborateurs](https://github.com/chenweize1998/fully-hyperbolic-nn/blob/main/mt/onmt/modules/hyper_nets.py)
construit self.weight avec nn.Linear et apprend aussi un facteur d'échelle.
Sa sortie est ensuite construite pour respecter la contrainte de Lorentz.
Le titre « fully hyperbolic » ne garantit donc pas que chaque paramètre
scalaire soit lui-même un point contraint sur la variété.

La [SPEC de Setharkk](SPEC.md) donne un critère plus précis pour notre
prototype : chaque position neuronale apprise est directement un point
de H4 ; les activations dépendent de distances géodésiques ; les agrégations
restent hyperboliques ; les mises à jour suivent la métrique riemannienne.
Les coordonnées de stockage et les probabilités restent des nombres réels.

Ce choix précis ne suffit pas à démontrer une nouveauté. Des prototypes
géométriques, des distances, des centroïdes et l'optimisation sur variété
sont des mécanismes connus. Une combinaison d'ingénierie peut être utile
sans constituer une contribution scientifique originale.

## Ce qui fonde effectivement la V1

La V1 utilise :

- Le modèle de Lorentz de l'espace hyperbolique, de courbure -1.
- Des positions apprises pour les observations, actions, clés/valeurs neuronales et sorties.
- Des activations softmax sur les distances géodésiques carrées.
- Des centroïdes normalisés de Lorentz et une connexion résiduelle géométrique.
- Un optimiseur adaptatif avec gradients riemanniens et transport des premiers moments.
- Un ensemble de trois prédicteurs et une sélection fondée sur leur désaccord.

Les mécanismes de Lorentz et d'optimisation ont aussi des références
explicites dans le [README V1](cortex_lab_v1/README.md).
Les huit neurones, la dimension 4, les températures, le rayon 2.5 et les
hyperparamètres sont des choix de prototype. Cette construction n'est
pas une reproduction complète des trois architectures citées.

La [revue de code](CODE_REVIEW_V1.md) et la [validation](INTRINSIC_VALIDATION.md)
ne démontrent ni une supériorité de la courbure, ni une évolution autonome.
Le budget de la V1 diffère de celui de la V0 : leurs scores ne permettent
pas d'isoler l'effet de la géométrie.

## Ce qui pourrait établir une contribution propre

Il faudrait identifier un mécanisme précis absent ou insuffisant dans
les travaux comparables, puis le tester. Pour l'objectif de Setharkk,
cela pourrait porter sur un apprentissage continu durable, le choix
d'objectifs améliorant des compétences mesurées, ou la coordination
d'agents partageant un état géométrique. Ces exemples sont des pistes
de recherche, pas des fonctions actuellement implémentées.

Une démonstration demanderait des références comparables en capacité,
des tâches nouvelles, une évaluation de l'oubli et du transfert,
ainsi que des ablations séparant géométrie, mémoire et sélection.
L'espace courbe, à lui seul, n'établit pas une intelligence autonome.
