# Première pièce : une mémoire qui apprend à distinguer

L'objectif est de découvrir une règle inconnue et de la réutiliser dans
une autre situation. La première pièce doit modifier durablement les
distinctions internes utilisées pour prédire les conséquences des actions.

Cette étape définit une règle candidate d'admission d'une distinction et
prépare son laboratoire. Elle n'implémente pas encore le réseau apprenant
qui propose ces distinctions.

## Exemple concret

Une porte présente toujours la même observation actuelle. Plus tôt dans
l'épisode, un signal a été reçu, parmi des événements sans rapport.
La bonne action, 0 ou 1, dépend de ce signal selon une règle inconnue.

Le laboratoire utilise des symboles numériques : un unique signal 0 ou 1,
des événements distracteurs, puis l'observation constante « sealed ».
Le générateur connaît la règle ; l'interface de l'apprenant ne la fournit pas.

Dans l'acquisition, les historiques ont 2 à 7 événements. Dans le transfert,
ils ont 13 à 33 événements, le signal arrive plus tard et des distracteurs
supplémentaires apparaissent. Le lien signal/action reste le même.
Le transfert teste ici un changement de présentation et de délai,
pas la généralisation à toute règle possible.

Un contrôle conserve les mêmes observations mais tire les résultats au
hasard, indépendamment du signal et de l'action.

## Ce que serait une distinction interne

L'expérience observée est (historique h, observation o, action a, résultat y).
Une unité regroupe provisoirement des expériences et porte une prédiction
p(y | o,a). Une proposition phi(h) sépare ce groupe en deux sous-groupes
et propose leurs prédictions conditionnelles.

Ce qui se modifierait durablement est la partition des expériences et
les prédictions associées. Une scission remplace une unité par deux :
le coût structurel est donc une unité supplémentaire.

Le mécanisme qui construit phi, sa représentation neuronale et sa
géométrie restent à définir. Les probabilités utilisées ci-dessous sont
des sorties à évaluer ; elles ne définissent pas les paramètres du futur réseau.

## Règle candidate de conservation

La proposition et ses prédictions sont construites avec des données passées,
puis figées avant un bloc de nouvelles expériences indépendantes.
La proposition ne peut pas utiliser les résultats futurs pour les prédire.

Sur n expériences, mesurer :

~~~text
g = moyenne_i log( p_proposition(y_i | h_i,o_i,a_i)
                  / p_parent(y_i | o_i,a_i) )

delta = log(1/epsilon) * sqrt( 2 * log(M/alpha) / n )

conserver si g - delta > lambda * cout_supplémentaire
~~~

Le gain est mesuré en nats par résultat observé. Les probabilités binaires
sont bornées entre epsilon et 1-epsilon pour borner le score.
Le terme delta est une borne conservative de Hoeffding, avec correction
par union sur au plus M comparaisons annoncées. Il suppose des observations
IID du bloc de validation et des prédicteurs figés avant ce bloc.

M compte toutes les propositions et tous les horizons examinés dans la
famille de tests, pas seulement celui dont le résultat est favorable.
Cette borne ne s'applique pas automatiquement à un environnement adaptatif
ou à une proposition retouchée après lecture de la validation.

La fonction first_piece/criterion.py applique cette décision avec :

- epsilon = 0.01 et alpha = 0.05 ;
- M = 1 000 comparaisons au maximum ;
- lambda = 0.01 nat par unité supplémentaire ;
- au moins 32 observations de validation dans chaque sous-groupe ;
- un budget maximum explicite d'unités.

Ce sont des valeurs de contrôle pour ce premier laboratoire, pas des
constantes universelles ou des réglages optimaux.

La décision est **acceptée**, **rejetée**, **en attente de données** ou
**bloquée par le budget**. Une assurance insuffisante ne devient pas
automatiquement une déclaration d'incapacité d'apprendre.

Fusionner et supprimer des distinctions demanderont leurs propres critères
de validation et de rétention ; ces décisions ne sont pas encore codées.

## Ce qui est préparé

| Élément | État |
|---|---|
| Monde séquentiel avec règle cachée | Implémenté |
| Présentations inédites pour le transfert | Implémentées |
| Monde aléatoire avec observations appariées | Implémenté |
| Validation prospective d'une proposition fournie | Implémentée |
| Sauvegarde complète du générateur et de son état aléatoire | Implémentée |
| Découverte autonome de phi | À construire |
| Réseau neuronal non euclidien de la nouvelle conception | À construire |
| Sauvegarde complète de ce futur apprenant | À construire |
| Dialogue, objectifs autonomes, cortex et agents | À construire |

Le snapshot du monde contient les informations privées nécessaires à la
reprise ; il n'est pas transmis comme observation à l'apprenant.

## Contrôles et durée

L'audit examine cinq graines, deux présentations et les deux types de monde,
aux horizons 100, 1 000 et 10 000 interactions.

Il utilise un oracle qui connaît la règle et un prédicteur constant.
L'oracle est un contrôle montrant que l'information permet de résoudre la
tâche ; il n'est pas un résultat d'apprentissage ni une référence équitable
pour un apprenant qui ne connaît pas la règle.

Le prédicteur constant fournit p = 0.5. Son Brier vaut 0.25.
Les comparaisons du futur apprenant utiliseront des références ayant
accès au même historique, conformément au protocole de mesure.

Les audits du laboratoire n'évaluent pas l'oubli ou la reprise d'un apprenant.
Ils enregistrent l'information disponible, les décisions du test statistique
et des contrôles. Le futur apprentissage devra être suivi sur ses propres
courbes d'acquisition, de transfert et de rétention.

## Exécution

Depuis la racine du dépôt, Python 3.11, sans dépendance supplémentaire :

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.audit --out first_piece/lab_runs/essai_1
~~~

Les fichiers produits sont config.json, summary.json, observations.jsonl
et des snapshots du monde. Le chemin de sortie doit être neuf.
Les observations publiques ne comprennent ni la règle cachée ni les
prédictions de l'oracle.

## Question de recherche suivante

Comment construire une distinction qui explique une erreur répétée,
sans mémoriser chaque épisode, et lui donner une représentation et des
opérations neuronales non euclidiennes ?

L'environnement et la règle d'admission constituent un outil pour examiner
cette question. Ils ne démontrent aucune originalité scientifique du futur
mécanisme. La géométrie, les règles de proposition et le budget de paramètres
devront être explicites avant de présenter un nouveau cœur comme implémenté.
