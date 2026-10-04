# Exigences du projet Setharkk

Ces exigences reprennent les demandes de l'utilisateur. La correction
essentielle est que le réseau lui-même doit être non euclidien.

## Exigence géométrique du réseau

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
| Réseau lui-même non euclidien | Implémenté dans cortex_lab_v1 ; validation CI requise |
| Apprendre des résultats de ses actions pendant une interaction | Implémenté dans le laboratoire de fichiers |
| Apprentissage continu avec reprise complète | À développer |
| Objectifs proposés par l'utilisateur et objectifs choisis par le système | À développer |
| Cortex avec un essaim d'agents comme extensions de lui-même | À développer |
| Dialogue | À développer |
| Agir sur des applications du PC | À développer |
| Petit budget de paramètres | V1 : 408 degrés de liberté intrinsèques pour trois modèles |

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
