# Cortex Lab V1 : réseau intrinsèque hyperbolique

Cette version répond à l'exigence que le réseau lui-même soit non euclidien :
ses paramètres neuronaux sont des points appris sur l'hyperboloïde H4.
Les couches utilisent la géométrie hyperbolique et l'optimiseur déplace
les paramètres sur cette variété.

La V0 reste disponible comme référence. Ses résultats publiés ne sont
pas les résultats de la V1.

## Architecture

Le modèle contient 34 points appris : prototypes des observations et
actions, huit clés et huit valeurs de neurones, puis deux prototypes pour
chacun des quatre bits de résultat.

~~~text
observations et action
    -> sélection de prototypes sur H4
    -> centroïde de Lorentz
    -> activations par distances géodésiques aux clés neuronales
    -> centroïde des valeurs neuronales
    -> connexion résiduelle par centroïde
    -> probabilités par distances aux prototypes de résultat
~~~

Les coefficients d'activation sont softmax(-distance² / température).
Ils dérivent de la géométrie ; aucune matrice nn.Linear apprise n'est
utilisée. Les sorties sont des probabilités binaires : trois présences
de fichiers et un succès, comme dans le laboratoire V0.

34 points sur H4 donnent 136 degrés de liberté intrinsèques par modèle.
Le stockage en coordonnées de Lorentz demande 170 nombres. L'ensemble
de trois modèles donne 408 degrés de liberté et 510 nombres stockés.

## Formules

~~~text
H4 = {p : <p,p>_L = -1, p0 > 0}
d(p,q)² = acosh(-<p,q>_L)²

centroïde(p_i,w_i) = S / sqrt(-<S,S>_L), S = somme_i w_i p_i

grad_R L(p) = G grad_ambiant L + <p,G grad_ambiant L>_L p
G = diag(-1,1,1,1,1)

mise à jour : exp_p(-pas * direction_tangente)
~~~

Le centroïde minimise la somme pondérée des cosh des distances ; ce n'est
pas en général la moyenne de Fréchet pour les distances carrées.

L'optimiseur adaptatif utilise un premier moment tangent, transporté
parallèlement après chaque déplacement, et un second moment scalaire par
point basé sur la norme riemannienne du gradient. Il utilise l'exponentielle
et une projection géodésique sur une boule de rayon 2.5 pour la stabilité.
Cette contrainte radiale privilégie l'origine ; l'invariance de l'optimisation
par changement d'origine est testée lorsque la contrainte est inactive.

L'initialisation utilise une carte tangente pour échantillonner des points.
La propagation du réseau n'effectue pas de passage log_origine suivi d'un
réseau linéaire euclidien. Les paramètres appris sont directement les points.

## Exécution Windows

Depuis la racine, avec l'environnement Python déjà installé pour la V0 :

~~~powershell
.\cortex_lab_v0\.venv\Scripts\python.exe -m unittest discover -s cortex_lab_v1/tests -v
.\cortex_lab_v0\.venv\Scripts\python.exe -m cortex_lab_v1.run --steps 200 --seeds 0 1 2
~~~

Un environnement séparé peut être créé avec cortex_lab_v1/requirements.txt.
CPU par défaut ; --device cuda nécessite une version CUDA de PyTorch.
Le GPU de l'utilisateur n'est pas validé par les runners CPU de la CI.

## Vérification

Les tests portent sur les paramètres et états sur H4, les distances et
leurs dérivées, le transport des moments, la descente géométrique,
l'invariance du réseau par isométrie, l'apprentissage d'opérations réellement
exécutées et l'indépendance des instantanés.

Le test d'apprentissage utilise les 32 couples du laboratoire comme données
d'entraînement. Il vérifie un mécanisme d'apprentissage ; le run séparé
utilise huit couples réservés par graine pour un diagnostic de généralisation.

Les sorties de cortex_lab_v1/cortex_runs contiennent config.json, splits.json,
summary.json, métriques, expériences, poids et mémoire. load_weights restaure
les prédictions dans un apprenant neuf ; le format ne restaure pas les
moments de l'optimiseur et la mémoire pour une reprise complète.

## Portée

Les [exigences du projet](../SPEC.md) distinguent la géométrie implémentée
des fonctions restant à construire. Dialogue, objectifs autonomes, mémoire
continue et coordination d'agents ne sont pas implémentés dans cette version.

Ce réseau à prototypes et son optimisation riemannienne utilisent des
familles de méthodes connues. Le laboratoire à trois bits ne démontre ni
une innovation scientifique ni un modèle du monde général. La V1 a un
budget différent de la V0 ; comparer directement leurs scores ne permet
pas d'attribuer une différence à la seule géométrie des paramètres.

Références pour les mécanismes :
- [Géométrie de Lorentz, Nickel et Kiela](https://arxiv.org/abs/1806.03417)
- [Optimisation adaptative riemannienne, Bécigneul et Ganea](https://arxiv.org/abs/1810.00760)
