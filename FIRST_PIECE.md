# Première pièce : distinguer des contextes à partir d'événements

La première pièce contient désormais un apprenant limité et mesurable :
il reçoit les événements un par un, apprend à prédire le résultat d'une
action et peut conserver une distinction fondée sur son passé.

Le [résultat mesuré](FIRST_PIECE_LEARNING_RESULTS.md) donne les courbes,
les contrôles, le transfert, la rétention et les vérifications de reprise.
La [première revue](CODE_REVIEW_FIRST_PIECE.md) reste l'état historique du
laboratoire avant cet apprenant.

## Ce qui change effectivement pendant l'apprentissage

Trois états sont distincts :

- Une mémoire temporaire de présence des dix symboles possibles, sous forme
  d'un masque de dix bits. Elle s'accumule pendant l'épisode et est effacée
  après son résultat.
- Quatre prototypes neuronaux par tâche, points appris sur la sphère S².
  Ils prédisent le résultat de deux actions dans deux routes possibles.
- Une distinction structurelle éventuelle : l'indice d'un événement dont
  la présence passée devient la route du réseau.

Le résultat observé déplace un prototype sur la sphère. La distinction
change ensuite les expériences envoyées à chaque neurone. Le choix du
symbole n'est pas donné à l'apprenant : il est proposé depuis les résultats
passés puis soumis à une validation indépendante de son ajustement.

La famille de propositions est volontairement bornée : « le symbole k
est-il apparu ? », pour k de 0 à 9. Une seule proposition est testée par
tâche, avec au plus une distinction conservée. Ce mécanisme ne découvre
pas encore des relations temporelles arbitraires ou un programme.

## Géométrie du réseau

Chaque prototype appris q est un point de S² :

~~~text
q appartient à R³ ; ||q|| = 1
d(q,c) = arccos(<q,c>)
~~~

Chaque sphère a une courbure intrinsèque positive +1. L'espace des
paramètres du réseau est un produit de sphères ; les plans mêlant deux
facteurs n'ont pas cette même courbure.

Les deux repères de sortie c0 et c1 sont fixes, orthogonaux.
La prédiction d'un neurone est :

~~~text
s = (d(q,c0)² - d(q,c1)²) / T
p(y=1) = sigmoid(s)
L = -y*log(p) - (1-y)*log(1-p)
~~~

T = 0.5 est fixe. Pour la mise à jour :

~~~text
grad_S L = (p-y) * 2/T * (Log_q(c1) - Log_q(c0))
q_suivant = Exp_q(-eta * grad_S L)
eta = 0.03 / sqrt(1 + nombre_de_mises_a_jour_du_neurone/100)
~~~

Les tangentes sont limitées à une norme de 0.2 pour stabiliser les pas.
Une renormalisation corrige uniquement l'arrondi numérique de Exp.

Tous les paramètres neuronaux réels appris sont ces points sphériques.
Il n'y a pas de matrice linéaire euclidienne apprise dans ce cœur.
Les masques, indices, compteurs, probabilités et choix de structure sont
des états discrets ou des scalaires ; ils ne sont pas tous des points courbes.

Il s'agit d'un petit réseau à prototypes géodésiques et routage structurel,
pas d'un réseau profond généraliste. Les tests vérifient la contrainte
sphérique, la tangence des mises à jour et l'équivalence des prédictions
et mises à jour après rotation simultanée des prototypes et repères.

La courbure est fixée, pas apprise. Cette construction ne démontre ni
une nouvelle famille scientifique ni un avantage de la sphère sur une
architecture euclidienne comparable.

## Arrivée des événements et action

StreamingWorld.next_event() émet seulement :

~~~text
{"kind": "token", "token": k, "task": t}
{"kind": "surface", "surface": "sealed", "task": t}
~~~

Aucun historique complet, règle cachée ou délai futur n'est fourni.
L'apprenant accumule lui-même les présences pendant les événements.
Il produit les probabilités des deux actions à l'arrivée de la surface.

Le laboratoire contient trois mondes :

- **Structuré** : la bonne action dépend d'un signal passé.
- **Bruit** : le résultat est indépendant du passé et de l'action.
- **Action seule** : le résultat dépend de l'action sans rôle du passé.

Dans l'acquisition, les historiques ont 2 à 7 événements. Le transfert
utilise 13 à 33 événements, de nouveaux distracteurs et des délais plus
longs, sans changer la règle.

Les identifiants de tâches sont explicitement observables. Les règles
contraires des tâches 0 et 1 ne doivent donc pas être devinées sans contexte.

## Proposition et contrôle ajusté

Les 256 premiers résultats servent à proposer une distinction.
La sélection classe les symboles selon la qualité empirique de la
prédiction conditionnée par leur présence et par l'action, avec lissage
des comptes. Chaque branche doit avoir au moins 32 exemples.

Ensuite deux modèles neufs sont ajustés sur les mêmes 256 enregistrements :

1. Le candidat route les événements avec la présence du symbole proposé.
2. Le contrôle route avec un tirage binaire indépendant de l'historique.

Les deux ont quatre prototypes S², le même état initial et le même
optimiseur. Chacun effectue exactement 256 mises à jour. Le contrôle
reçoit les mêmes événements, actions et résultats ; la relation entre
le passé proposé et sa route est supprimée.

Le contrôle est un retrait de la distinction dans la même architecture.
Il n'est pas une comparaison à toutes les autres formes possibles de
réseaux ou de mémoires.

## Validation prospective

Le candidat et son contrôle restent figés pendant les nouveaux exemples.
Les horizons de validation sont 128, 1 024 et 4 096 interactions, annoncés
avant l'exécution. Les actions d'apprentissage sont tirées au hasard
dans cette expérience, pour garder la distribution de validation IID.

~~~text
g = moyenne log(p_candidat(y) / p_controle_ajuste(y))
delta = log(1/epsilon) * sqrt(2 * log(2*M/alpha) / n)
conserver si g - delta > lambda * unite_supplementaire
~~~

epsilon = 0.01, alpha = 0.05, M = 1 000 et lambda = 0.01.
La borne couvre les deux queues de chaque comparaison. Chaque branche
doit aussi compter au moins 32 exemples de validation.

Deux racines sont réservées par défaut et le budget est de quatre unités
structurelles : au plus une scission par tâche, pour deux tâches.
Le budget est vérifié avant l'admission.

Le réseau courant de secours continue son apprentissage durant cette
phase ; ses changements n'affectent pas les deux modèles figés évalués.
Lors d'une admission, le candidat ajusté sur le passé remplace le réseau
courant. Le bloc qui décide l'admission ne sert pas à entraîner ce candidat.
Les interactions suivantes reprennent ses mises à jour.

Une attente au dernier horizon devient **inconclusive**, sans créer la
distinction et sans conclure à une impossibilité générale. Cette version
ne cherche pas une deuxième proposition après cet essai.

## Vérifier que la distinction et la mémoire servent

L'expérience entraîne en parallèle deux apprenants :

- La version complète utilise la distinction lorsqu'elle est admise.
- La version sans distinction effectue la même recherche et les mêmes
  ajustements, puis utilise le contrôle au moment de cette admission.

Les deux reçoivent les mêmes événements, actions et résultats pendant
l'apprentissage. Le nombre de prototypes et de mises à jour est égal.
Les évaluations utilisent des mondes indépendants et des clones dont
les paramètres ne sont pas entraînés.

Un troisième contrôle conserve les poids de la version complète mais
efface la mémoire avant chaque événement, y compris avant la surface.
Il vérifie si le maintien de l'information passée contribue à l'action.
Ce retrait de mémoire n'est pas un modèle réentraîné.

Le monde « action seule » vérifie que le système peut améliorer ses
prédictions sans admettre une distinction temporelle inutile. Le monde
aléatoire vérifie l'absence d'admission dans les budgets effectivement testés.

## Taille et sauvegarde

Par tâche : quatre points appris, douze coordonnées stockées et huit
degrés de liberté intrinsèques. Pour deux tâches actives : huit points,
vingt-quatre coordonnées et seize degrés de liberté.

Pendant la validation d'une tâche, le candidat et le contrôle ajoutent
huit points temporaires. Avec deux tâches connues et une validation en
cours, cela donne seize points, quarante-huit coordonnées et trente-deux
degrés de liberté temporairement stockés. Deux validations simultanées
pourraient atteindre vingt-quatre points.

Ces comptes ne sont pas toute la mémoire : les enregistrements de
proposition, les probabilités de validation, les compteurs et les
générateurs aléatoires font aussi partie de l'état sauvegardé.
Leur taille est bornée par la configuration et doit rester comptée.

Le checkpoint de l'apprenant conserve les points, compteurs, distinction,
mémoire de l'épisode en cours, modèles figés, enregistrements, décisions
et état aléatoire. Le monde conserve sa séquence privée et sa position.
Le fichier de l'expérience conserve aussi le générateur des actions et
les mesures des horizons atteints.

La reprise JSON du monde et de l'apprenant est testée pendant une validation
et au milieu d'un épisode. Il n'y a pas encore de commande permettant de
prolonger automatiquement toute l'expérience depuis son checkpoint.

La rétention teste des réseaux séparés par identifiant de tâche. Elle
ne mesure pas encore l'absence d'interférence dans des neurones partagés.

## Raccordement aux pièces suivantes

`FirstPieceAdapter` reçoit des observations versionnées et produit des
prédictions liées à leur événement, contexte et révision du modèle.
Les agents proposent un candidat ; le coordinateur le lie à un exécuteur.
Le résultat observé revient par identifiant de requête. Les doublons
n'ajoutent pas de mise à jour et une erreur technique ne devient pas
une étiquette négative.

L'[architecture commune](SYSTEM_ARCHITECTURE.md) décrit les contrats,
les responsabilités et les limites de reprise. L'adaptateur actuel garde
un flux et une action en attente ; il n'exécute aucune opération réelle.

Le [protocole de la prochaine révision](FIRST_PIECE_NEXT_PROTOCOL.md)
vise l'ordre des événements puis le remplacement d'une règle dans le
même contexte. Le masque de présence actuel ne remplit pas ce protocole.

## Exécution

Python 3.11, sans dépendance supplémentaire :

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.learning_run --seeds 0 1 2 3 4 --out first_piece/lab_runs/apprentissage_1
~~~

Le chemin de sortie doit être neuf. Les horizons d'apprentissage sont
100, 1 000 et 10 000 interactions. Après la tâche structurée 0, la tâche
1 reçoit 10 000 interactions supplémentaires ; la tâche 0 est ensuite
réévaluée.

Le dialogue, les objectifs choisis par le système, la création d'agents,
les opérations sur le PC et l'apprentissage de règles plus générales
restent les étapes suivantes du projet.
