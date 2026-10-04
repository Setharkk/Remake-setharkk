# Première pièce révisable : ordre des événements et changements cachés

Cette révision s'ajoute à l'apprenant de présence conservé comme référence.
Elle utilise les mêmes contrats JSON via `TemporalAdapter`, avec l'identité
`first_piece.first-order-s2.v1`. Le modèle, les buts et les actions réelles
restent des pièces distinctes ; cette révision traite un apprentissage borné.

## Ce qui est appris et ce qui est choisi

Les paramètres neuronaux restent les prototypes sur S² et les mises à
jour géodésiques de la [première construction](FIRST_PIECE.md).
Il n'y a pas de matrice euclidienne apprise ajoutée dans le cœur.

La mémoire de l'épisode comprend :

- 10 bits de présence ;
- 45 bits décrivant, pour chaque paire a < b, si la première apparition
  de a précède celle de b ;
- le contexte, un tirage indépendant, un compteur et la phase de l'épisode.

Lors de la première arrivée de b, les bits a-avant-b sont fixés pour
les a déjà vus. Les répétitions ne modifient pas ce premier ordre.
Aucune liste d'événements passée n'est stockée par l'apprenant.
L'absence d'un des deux symboles donne une route fausse ; leur présence
est conservée séparément.

La famille contient 55 prédicats : 10 présences et 45 ordres orientés.
L'orientation contraire est représentable par les prédictions de sortie.
Il s'agit d'une grammaire explicitement programmée, pas de la découverte
d'une relation temporelle arbitraire.

Les 256 derniers résultats et leurs statistiques suffisantes servent à
classer les prédicats par log-vraisemblance conditionnée par l'action,
avec comptes lissés. Chaque branche exige 32 exemples. Un candidat est
ajusté sur cette fenêtre ; un contrôle de même taille est ajusté sur
les mêmes actions et résultats avec une route aléatoire indépendante.

Chaque contexte conserve deux modèles à quatre points S² :
le modèle de prédiction et le contrôle sans relation. Ils reçoivent
le même nombre de mises à jour et sont remplacés ensemble lorsqu'une
proposition est admise. Le contrôle permet une comparaison de lecture
avec exactement le même budget de paramètres et d'ajustement.

## Déclenchement et protection du modèle courant

Après une fenêtre complète, une tentative devient possible si la perte
de Brier moyenne du modèle courant dépasse 0.12. Ce seuil et la fenêtre
sont des choix heuristiques annoncés, pas une théorie universelle de dérive.

Le candidat et son contrôle sont figés pendant la validation. Le modèle
courant et son contrôle continuent leurs mises à jour après chaque résultat.
Le score du modèle courant est enregistré avant sa mise à jour : le
candidat est comparé aux prédictions réellement utilisées, sans connaissance
du résultat courant. Les horizons sont
128, 1 024 et 4 096 nouveaux résultats.

Deux comparaisons doivent passer :

1. Le candidat apporte un gain sur son contrôle ajusté sans relation.
2. Il apporte un gain sur le modèle courant, avant son remplacement.

Cette seconde condition évite d'adopter régulièrement un modèle neuf
moins précis qu'un modèle courant qui fonctionne déjà.

Si un gain empirique est au plus 0.01 à un horizon, l'essai s'arrête avec
le statut `futile`. Cela économise du temps de gel ; cela ne conclut pas
que la relation serait impossible ou inutile pour toujours.
À 4 096 sans conclusion suffisante, l'essai est `inconclusive`.

Après une fin d'essai, 256 interactions au minimum précèdent une nouvelle
tentative. Le modèle courant poursuit ses mises à jour. Un nouvel essai
emploie les données récentes et un bloc prospectif neuf. Les résultats
du bloc qui admet un candidat ne servent pas à ajuster ce même candidat.

Une admission remplace la distinction et les modèles du contexte existant.
L'ancienne allocation est libérée. Une inversion peut aussi être apprise
par les mises à jour des mêmes prototypes : le protocole distingue
l'adaptation des poids du remplacement d'une relation.

## Sens de la borne sous un changement caché

La fonction de calcul du gain et de la borne est partagée avec le
laboratoire précédent. Son interprétation change ici : elle concerne
la moyenne des gains conditionnels dans le bloc passé, pas une assertion
IID sur un régime futur.

Soit X_i le gain de log-score entre deux prédictions produites avant
le résultat courant, avec la probabilité du résultat bornée entre
epsilon et 1-epsilon. Le candidat et son contrôle sont figés ; le modèle
courant peut dépendre des résultats passés, jamais du résultat courant.
Pour epsilon=0.01, |X_i| <= L = log(1/epsilon).
Conditionnellement au passé précédant l'épisode i, X_i a une espérance
mu_i. Une borne de Hoeffding-Azuma pour les différences bornées donne :

~~~text
|moyenne(X_i) - moyenne(mu_i)| <=
    L * sqrt(2 * log(2*M/alpha) / n)

admission si gain - borne > 0.01
~~~

La borne traite une moyenne conditionnelle sur le bloc même si les
distributions varient ; elle ne garantit pas sa stabilité après ce bloc.
Les évaluations indépendantes de chaque régime fixe servent à mesurer
la performance après le changement.

alpha=0.05. Le budget global vaut
M = 2 comparaisons * max_contexts * max_attempts * 3 horizons.
Avec deux contextes et 32 tentatives par contexte, M=384.
Les débuts d'essai et choix de candidat utilisent seulement le passé.
Un arrêt pour futilité ne crée aucune admission supplémentaire et toutes
les tentatives, y compris celles sans support, consomment leur budget.

Les branches doivent compter chacune 32 exemples de validation.
Les unités structurelles comptent les racines réservées et une relation
éventuelle par contexte. Une relation remplaçant une relation existante
utilise son allocation, sans en ajouter une nouvelle.

## Budgets complets et limites

Configuration par défaut : 2 contextes, 4 unités structurelles,
32 tentatives maximum par contexte, fenêtres d'ajustement de 256 lignes,
au plus 4 096 lignes transitoires par comparaison.

Par contexte, les modèles actifs et leur contrôle comptent 8 points S²,
24 coordonnées, 16 degrés de liberté. Une tentative ajoute 8 points
temporaires : 16 points, 48 coordonnées et 32 degrés de liberté.
Avec deux contextes connus et une seule validation, cela donne 24 points
stockés ; deux validations peuvent atteindre 32 points.

La mémoire discrète, les fenêtres, les modèles temporaires, l'état
aléatoire et le journal borné des décisions font partie du checkpoint.
Les compteurs sont bornés aux entiers exacts représentables en JSON
entre langages. Le budget de tentatives est un budget de vie de ce
prototype : une fois épuisé, les mises à jour continuent mais la recherche
de nouvelles relations s'arrête. Son renouvellement durable demandera
une politique et une allocation statistique distinctes.

Les réseaux restent séparés par contexte. Leur conservation ne démontre
pas une absence d'interférence dans des neurones partagés.
Les candidats peuvent rester inadaptés si le monde change durant leur
validation. Le modèle servi continue à apprendre ; la sélection peut
néanmoins retarder le remplacement d'une relation et ce délai est mesuré.

La reprise conserve l'ordre partiel, les fenêtres, les modèles figés et
les générateurs aléatoires. Le format refuse une relation cyclique,
un budget incohérent ou une prédiction étrangère. Un checkpoint de présence
n'est pas converti silencieusement en mémoire d'ordre.

## Protocole exécuté par le benchmark

Cinq graines, horizons 100, 1 000 et 10 000 avant et après le changement :

- Monde stationnaire, sans changement après 10 000 interactions.
- Inversion de la bonne action, même relation et même contexte.
- Changement de relation : 0 avant 1 devient 2 avant 3, même contexte.
- Bruit indépendant : 10 000 interactions.
- Action seule : 10 000 interactions.

Tous les épisodes contiennent les quatre symboles 0..3, chacun une fois,
dans une permutation aléatoire, avec des distracteurs indépendants.
Les présences ne suffisent pas. Le monde transmet des tokens et une
surface, jamais la relation ciblée, la règle ou la date d'un changement.

Les actions d'apprentissage sont aléatoires. Des clones évalués sans
apprentissage comparent le modèle complet, son contrôle ajusté sans ordre,
une intervention effaçant les relations de l'épisode et l'ancien apprenant
de présence. Cette dernière référence a un budget différent, publié ;
la comparaison appariée principale concerne le contrôle interne ajusté.

Les mesures primaires utilisent 512 épisodes indépendants par horizon.
Le transfert utilise 1 024 épisodes avec délais prolongés et nouveaux
distracteurs. Un autre contexte stable reçoit 2 000 interactions avant
le changement du premier, puis sa rétention est évaluée sur 512 épisodes.
La conservation porte sur son état complet, pas seulement ses poids.

Le délai de récupération est sondé tous les 256 résultats, sur 128
épisodes indépendants, jusqu'au premier succès >=0.95 et Brier <=0.02.
C'est une mesure opérationnelle échantillonnée, pas un temps exact ni
une nouvelle garantie de confiance statistique.

Les pics de ressources publiés sont échantillonnés. Les plafonds de
structures, fenêtres et tentatives sont contrôlés par le code et les tests.
Les résultats et checkpoints sont écrits après chaque horizon et condition,
pour conserver les mesures déjà obtenues lors d'une interruption.

~~~text
python -m unittest discover -s first_piece/tests -v
python -m first_piece.temporal_run --seeds 0 1 2 3 4 --out temporal-run-1
~~~

Les résultats mesurés seront publiés séparément ; le code de l'expérience
ne suffit pas à démontrer une capacité générale d'autonomie.
