# Cortex Lab V0

Premier morceau expérimental du projet Setharkk : un petit modèle prédit les
effets de ses actions sur des fichiers réels et choisit des expériences pour
réduire son incertitude.

Le laboratoire observe trois bits : présence de A/item.txt, B/item.txt et
A/renamed.txt. Les quatre actions disponibles sont créer, déplacer, renommer
et lire A/item.txt. Les résultats viennent des opérations effectivement
exécutées. Chaque expérience utilise des fichiers neufs dans un sous-dossier
du répertoire de résultats.

Chaque modèle contient **72 paramètres entraînables**. L'ensemble contient
trois modèles, soit **216 paramètres**. Ce budget est possible grâce à un
état et à des opérations très simplifiés. La mémoire d'expériences, les
primitives de fichiers et la bibliothèque PyTorch ont aussi une complexité
qui ne se résume pas au nombre de paramètres.

## Installation sous Windows

Python 3.11 ou 3.12 recommandé. Exécuter depuis la racine du dépôt :

~~~powershell
py -3.11 -m venv cortex_lab_v0/.venv
.\cortex_lab_v0\.venv\Scripts\python.exe -m pip install -r cortex_lab_v0/requirements.txt
.\cortex_lab_v0\.venv\Scripts\python.exe -m unittest discover -s cortex_lab_v0/tests -v
.\cortex_lab_v0\.venv\Scripts\python.exe -m cortex_lab_v0.run --steps 200 --seeds 0 1 2
~~~

Le CPU est le choix par défaut : ce petit réseau ne nécessite pas de GPU.
Pour utiliser la RTX, installer une version CUDA de PyTorch avec les
instructions de https://pytorch.org/get-started/locally/, puis ajouter
--device cuda. Aucun pilote ni aucune installation CUDA ne sont modifiés
par le programme.

Un premier essai court :

~~~powershell
.\cortex_lab_v0\.venv\Scripts\python.exe -m cortex_lab_v0.run --steps 40 --seeds 0
~~~

Sous Linux :

~~~bash
python3 -m venv cortex_lab_v0/.venv
cortex_lab_v0/.venv/bin/python -m pip install -r cortex_lab_v0/requirements.txt
cortex_lab_v0/.venv/bin/python -m unittest discover -s cortex_lab_v0/tests -v
cortex_lab_v0/.venv/bin/python -m cortex_lab_v0.run
~~~

## Expérience et contrôles

Le programme compare quatre conditions :

| Géométrie | Sélection des expériences |
|---|---|
| Hyperbolique | Gain d'information estimé |
| Hyperbolique | Aléatoire |
| Euclidienne | Gain d'information estimé |
| Euclidienne | Aléatoire |

Les architectures ont le même nombre de paramètres, la même initialisation
par membre et les mêmes budgets. Les modèles voient des séquences
d'expériences différentes lorsque la stratégie de sélection diffère.

Les 32 couples état/action possibles sont observés par le banc d'évaluation.
Pour chaque graine, huit couples sont réservés au contrôle : un succès et
un échec par action. Ils sont exclus de l'entraînement et de la sélection.
Le sélecteur reçoit les observations et actions candidates, jamais leurs
résultats. Le contrôle représente une interpolation sur un monde minuscule.

Huit expériences de démarrage sont communes aux quatre conditions.
Ensuite, la sélection active choisit un couple selon le gain d'information,
avec 12 % d'exploration aléatoire. Le générateur du laboratoire prépare
l'état demandé. Les buts de la V0 sont donc choisis dans un catalogue fini :
apprendre les effets d'une des quatre opérations.

Après chaque expérience, trois petites mises à jour par modèle sont
effectuées avec un échantillonnage de la mémoire. La mémoire conserve au
maximum 2048 expériences.

## Mathématiques implémentées

La courbure hyperbolique est fixée à -1. Les deux variantes produisent les
mêmes vecteurs dans la carte de l'origine :

- q = 0.8 tanh(E observation)
- w = 0.4 tanh(F [q ; action])

Dans la variante euclidienne, le prochain état est q + w.

Dans la variante hyperbolique, le point z est exp_origine(q). Le vecteur
(0, w), tangent à l'origine, est transporté parallèlement jusqu'à z, puis
exp_z réalise la transition. Le décodeur reçoit log_origine du point obtenu.

En notation de Lorentz :

~~~text
<x,y>_L = -x0*y0 + somme_i(xi*yi)
H = {z : <z,z>_L = -1, z0 > 0}

exp_origine(q) = (cosh(r), sinh(r)/r * q), r = ||q||

v0 = somme_i(zi*wi)
v_spatial = w + v0/(1+z0) * z_spatial

exp_z(v) = cosh(||w||)*z + sinh(||w||)/||w|| * v
~~~

Le transport conserve la norme de w. Des limites numériques régulières
traitent les vecteurs nuls. L'encodage et la longueur du déplacement sont
bornés pour limiter les problèmes numériques. Les coefficients 0.8 et 0.4
sont des choix de stabilisation du prototype.

Les quatre sorties binaires sont les trois présences après l'action et son
succès. Chaque membre est entraîné avec une entropie croisée binaire
moyenne, puis Adam. Les poids des couches sont des paramètres euclidiens ;
les états intermédiaires et les transitions hyperboliques suivent la variété.

Le gain d'information est :

~~~text
U(o,a) = H(moyenne_k p_k(Y | o,a))
         - moyenne_k H(p_k(Y | o,a))
~~~

Les 16 résultats binaires sont énumérés. Chaque membre prédit des bits
conditionnellement indépendants ; l'entropie de leur mélange est calculée
explicitement. U mesure l'information sur l'identité d'un membre de
l'ensemble. L'ensemble est une approximation heuristique d'incertitude,
sans calibration bayésienne garantie. Le coût des expériences est traité
comme identique dans cette V0.

## Lire les résultats

Les sorties se trouvent dans cortex_lab_v0/cortex_runs/<identifiant>/ :

- config.json : paramètres et environnement logiciel ;
- splits.json : situations d'entraînement et de contrôle ;
- summary.json : résultats par graine et moyennes descriptives ;
- seed_*/<condition>/metrics.csv : courbe de progression ;
- experiences.jsonl : observation, prédiction avant action et résultat réel ;
- weights.pt : poids sauvegardés ;
- replay.json : mémoire d'expériences ;
- files/ : fichiers réellement manipulés par cette condition.

Dans metrics.csv :

- **brier** : erreur moyenne des probabilités sur le contrôle ; plus faible
  est meilleur ;
- **nll** : perte logarithmique du mélange sur le résultat complet ;
- **exact_accuracy** : les quatre bits sont simultanément corrects ;
- **success_accuracy** : prédiction correcte de la réussite de l'opération ;
- **brier_action_0..3** : erreurs par compétence, pour repérer les régressions ;
- **weights_changed_l2** : amplitude du changement depuis l'initialisation ;
- **gradient_norm** : norme du gradient avant écrêtage ;
- **optimizer_updates** : nombre réel de mises à jour.

Un changement de poids seul ne démontre pas un apprentissage utile.
Vérifier la baisse de l'erreur sur le contrôle et comparer les références
calculées **sur les mêmes cas réservés** : probabilités uniformes et
prédiction que les fichiers restent inchangés.

La V0 sauvegarde les poids et les expériences. Elle commence une expérience
comparative neuve à chaque lancement ; une reprise complète des optimiseurs
et du fonctionnement continu reste à développer.

## Portée des conclusions

Ce laboratoire teste le mécanisme d'apprentissage et le choix des
expériences. Il ne dispose pas encore de dialogue, d'agents d'applications,
de nouvelles compétences inventées ou de contrôle général du bureau.
Il n'est pas un modèle du monde complet.

Les trois graines par défaut et huit situations réservées constituent un
diagnostic. Les résultats ne suffisent pas à établir une supériorité générale
de la géométrie hyperbolique. Une baisse d'erreur ici doit ensuite être
confirmée sur des environnements plus variés.

## Validation

Les tests fournis couvrent la géométrie et ses dérivées, les opérations
réelles de fichiers, la séparation des données, le gain d'information,
l'amélioration de prédictions et la sauvegarde des poids.

Lors de la préparation, les formules géométriques ont été contrôlées
séparément dans un environnement JavaScript sur 1000 états. L'erreur
maximale de conservation de norme était inférieure à 5e-12.

Une simulation numérique séparée, sur une seule séparation de données et
avec gradients numériques, a réduit le Brier de 0.2455 à 0.1656 pour la
version hyperbolique et à 0.1223 pour la version euclidienne. Cette simulation
n'exécutait ni ce code PyTorch ni les opérations Windows. Elle ne constitue
pas une validation de ce programme. La version euclidienne y faisait mieux.

Les tests Python doivent être exécutés localement ou par la CI ; leur
résultat effectif est à vérifier dans les journaux correspondants.
