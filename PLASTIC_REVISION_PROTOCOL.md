# Réutilisation plastique, délais et montée à l'échelle : protocole

Ce protocole est fixé avant les nouvelles mesures. La référence est
le mode calibré de format 5, moteur bf15bec. La révision reste sur S²,
avec la même famille de prédicats, le même nombre de prototypes, deux
gradients par retour et le même nombre de gradients de replay par essai.

## Transfert et contrôle

Les candidats utilisent les poids de la banque active plastique.
Les routes anciennes sont regroupées selon les routes du programme proposé
sur les épisodes du buffer. Chaque prototype proposé est une moyenne
intrinsèque approchée sur S², huit itérations au maximum. Les poids de cette
moyenne sont des effectifs d'épisodes, pas une matrice neuronale apprise.

Un prototype est conservé si au moins huit labels de son groupe sont
disponibles et si sa log-vraisemblance tronquée sur le passé est strictement
meilleure que celle du prototype neutre p=0,5. Sinon, ce prototype reste
neutre. Une moyenne antipodale indéfinie reçoit aussi ce repli explicite.

Le contrôle suit le même test depuis ses prototypes plastiques, avec son
routage aléatoire. Les compteurs des deux optimiseurs sont remis à zéro
dans les candidats. Les banques sources et la compétence protégée ne sont
pas changées par l'initialisation. Tous les gradients de replay sont ensuite
identiques en nombre au budget historique. Les calculs de moyenne, sélection
et lecture ajoutent du travail ; ils ne sont pas des gradients cachés.

## Contrôle du bruit de contexte

Une première exécution e3efcb9 a révélé une régression : sous des taux de
résultat indépendants de l'action mais différents selon le contexte, un
programme de taux de base pouvait remplacer la compétence. Le protocole
garde ses critères et ajoute un contrôle conditionnel avant la nouvelle
exécution ; cette correction sera séparée des premiers chiffres partiels.

Pour les nouvelles validations, la pertinence compare le candidat à
q_contexte=(positifs_fit+1)/(labels_fit+2), figé AVANT les futurs labels.
Un contexte absent du fit reçoit le même estimateur calculé sur tout le fit.
Ainsi, prédire seulement le taux du contexte ne démontre pas un apport
du programme. Les banques de contrôle sphériques restent entraînées avec
le même budget et reprises comme banques de travail. Le contrôle statistique
conditionnel est une fréquence de labels, pas un paramètre neuronal appris.

L'ablation « nouvelles bornes » regroupe la référence figée, le contrôle
conditionnel, les regards, leurs bornes et l'examen du candidat. Elle ne
permet pas d'attribuer leur gain à chacun de ces mécanismes isolément.

## Références et bornes

Avant la première admission, la banque plastique servie est copiée et figée
pendant le nouvel essai. Après une admission, la banque protégée joue déjà
ce rôle. Les banques de travail continuent à apprendre.

Les réseaux proposés et contrôles sont figés après leur fit. Leur gain
g_i pour un résultat Bernoulli a deux valeurs, connues avant le label.
L'amplitude conditionnelle vaut w_i=|logit(p_i)-logit(q_i)|, avec probabilités
tronquées à [0,01 ; 0,99]. Une amplitude maximale W est calculée AVANT
validation, sur toutes les actions et une sur-approximation des routes
possibles. Les égalités de contexte prennent leur valeur réelle ; toutes
les autres combinaisons de vérité sont incluses. Le contrôle conditionnel inclut tous
ses taux de contexte et le taux de repli. Une référence mobile conserve W universel.

À chaque retour principal, V_n=somme(w_i²) est calculé depuis les probabilités
avant le label. Pour pertinence et amélioration, aux regards déclarés n :

- L=log(2 * 3 * nombre_de_regards * tentatives_par_bloc * 4 / alpha_bloc) ;
- lambda_0=sqrt(8 L / (n W²)) ;
- quatre lambda fixés d'avance : lambda_0 * (1, 2, 4, 8) ;
- rayon=min_lambda (L/lambda + lambda V_n/8)/n ;
- borne inférieure=gain_moyen-rayon ; si W=0, rayon=0.

L'inégalité conditionnelle de Hoeffding donne
E[exp(lambda*(g_i-E[g_i|passé et entrée])) | passé et entrée]
<= exp(lambda² w_i²/8). Les quatre réglages et tous les regards se partagent
le risque par union. La sélection du rayon après observation de V_n n'est
donc pas une optimisation sans pénalité. Cela borne la moyenne des gains
conditionnels sur les entrées observées, pas une distribution future arbitraire.

Pour le complément d'un essai ciblé, la somme prévisible V est également
retenue. À l'époque j=floor(log2(n_autres)), lambda_0 utilise 2^j à la place
de n, et L=log(2*3*tentatives_par_bloc*4*(j+1)*(j+2)/alpha_bloc).
Les quatre lambda de chaque époque sont fixés avant les labels. L'inégalité
de Ville donne la validité uniforme dans le temps pour chaque lambda ;
l'union des époques utilise somme_j 1/((j+1)*(j+2))=1. Cela conserve une
borne uniforme dans le temps, avec les largeurs effectives des entrées.
Le premier moteur corrigé 973d034 échouait au délai (18 000 pour la graine 0)
malgré la conservation réussie. Les critères demeurent ceux déclarés.

Les seuils de pertinence, amélioration, conservation et support ne
sont pas abaissés. Les nouveaux regards sont 128, 512, 1 024, 2 048, 4 096, 8 192,
16 384 retours principaux. Risque à vie, blocs et archives restent sommables.
Le journal garde 16 recherches et au plus 112 décisions par défaut.

## Remplacement d'un candidat dépassé

Un candidat encore en attente aux horizons 512 ou 1 024 reçoit un examen
de la fenêtre récente, avant ou après la première admission. Les essais
ciblés gardent leur portée et leur validation du complément. La recherche
emploie la même famille de programmes et le même score pénalisé de fit.
Si un autre programme a un score supérieur d'au moins 0,02, ou si l'ancien
n'a plus le support minimal de fit, l'essai est clos comme « superseded ».
Le nouvel essai peut commencer au retour suivant, avec son propre risque
et de nouveaux labels de validation. Aucun risque dépensé n'est remboursé.

Cet examen exploite le passé pour proposer ; il ne constitue pas une
admission. Les regards statistiques et les seuils restent obligatoires.
Son travail de recherche est journalisé séparément. L'archive héritée
regroupe cette clôture avec les essais inconclusifs ; un compteur séparé
en conserve le sous-total exact.

Le moteur 4467089 conservait encore un délai de 18 000 sur la graine 0 :
le bon candidat était disponible, mais la preuve d'amélioration échouait
à 1 024 et le regard suivant était 4 096 retours principaux. Le regard
2 048 est ajouté avec sa propre part de risque. Le plafond détaillé devient
112 décisions, sans agrandir les banques neuronales.

## Reprise et capacité

Format 6, identité first_piece.plastic-revision-s2.v1. L'import explicite
depuis le format 5 conserve une validation déjà commencée avec ses anciens
horizons, bornes, banques, compteurs et requêtes. La frontière de politique
s'applique seulement aux nouvelles tentatives. Les formats plus anciens
suivent d'abord leurs imports documentés.

Les amplitudes sont recomputées depuis les réseaux figés lors d'une reprise
en validation. Les sommes V sont contrôlées contre leurs bornes et les regards
passés, sans prétendre reconstituer tous les labels historiques manquants.
Les métadonnées et checkpoints ne constituent pas une preuve cryptographique.

Quatre actions et huit routes : 96 points S² en service après admission et
160 au maximum pendant une validation. Avant la première admission, la
référence figée ajoute 32 points pendant l'essai, remplaçant dans ce budget
la banque protégée encore absente. Cache statistique et buffers sont séparés.

## Comparaison principale et ablations

Reprendre les douze cas du protocole de calibration : bruit initial,
rétention, six changements et taux de bruit variables, graines 0/1/2,
16 symboles, quatre contextes, quatre actions. Modes calibré et révisé,
mêmes actions exploratoires uniformes et mêmes labels. Toutes les phases,
journaux, courbes, scores et reprises sont publiés.

Les sondes du signal après bruit initial sont espacées de 1 000 retours
globaux. Publier la première admission et le premier point où les quatre
contextes dépassent 95 %, confirmé au point suivant. Objectif annoncé :
le pire délai confirmé de la révision <= 12 000 retours globaux de signal.
Le critère ne confond pas une admission partielle avec une compétence complète.

Reprendre aussi les critères de calibration : Brier du bruit de rétention
<= 0,205, perte logarithmique tronquée <= 0,62 ; Brier structuré par contexte
<= 0,025 à 500 nouveaux retours/contextes ; conservation >=95 % ;
toutes les phases de changement finissent >=95 % et les autres contextes
restent corrects aux sondes ; aucune admission dans le bruit indépendant.

Ablations supplémentaires sur les trois cas de bruit initial :
initialisation neutre avec nouvelles bornes ; initialisation plastique avec
anciennes bornes. Même nombre de gradients de replay par fit. Publier
délais, erreurs et coûts sans supposer que le transfert aide chaque graine.
Les économies de gradients dues à moins de tentatives sont distinguées
d'un changement du budget de chaque tentative.

## Montée à l'échelle de la révision

La nouvelle révision seule reçoit trois graines, 64 symboles, 16 contextes
entraînés, quatre actions, capacité 17 contextes pour une sonde de transfert.
Les contextes partagent la règle initiale ; seul le contexte 0 change.

Par graine : 16 000 retours indépendants, 160 000 structurés (10 000/contexte),
64 000 indépendants (4 000/contexte), 32 000 structurés de récupération
(2 000/contexte), puis 160 000 avec changement du contexte 0
(10 000/contexte). Total 432 000 retours. Ce temps n'est pas raccourci
après les résultats.

Sondes sans apprentissage, 128 épisodes/contexte :
initial 100/1 000/2 500/10 000 labels/contexte ;
bruit 1 000/2 000/4 000 ;
récupération 512/1 024/2 000 ;
changement 100/500/1 000/2 000/4 000/6 000/10 000.
Sonde finale du contexte neuf 16 : 512 épisodes, zéro label d'apprentissage.

Critères : compétence finale initiale et après changement >=95 % dans chaque
contexte ; conservation >=95 % pendant le bruit ; aucun remplacement sous
bruit ; Brier bruit moyen <=0,205 et perte tronquée <=0,62 ; récupération
structurée Brier <=0,025 à 512 labels/contexte ; contexte neuf >=95 %.
Au plus 160 points S², 4 096 lignes retenues, 4 096 probabilités en cache,
16 recherches détaillées et 112 décisions.

Reprise en validation ciblée reproduisant 1 024 retours futurs.
Comparer Windows/Linux, trois graines identiques, bibliothèque standard
Python 3.11, aucune mesure de la RTX. Durées, tailles JSON, système et version
Python exclus de la comparaison numérique à tolérance 1e-10.

Ces expériences restent synthétiques. Elles ne prouvent pas un dialogue,
une autonomie générale, une nouveauté scientifique ou un avantage euclidien.

## Graines supplémentaires après les révisions

Le test rapide ajoute les graines 17 et 23, choisies avant leur exécution
pour observer la sensibilité au-delà des graines de développement 0/1/2.
Les flux, budgets et sondes restent identiques. Le seuil de délai annoncé
s'applique aux trois graines initiales ; les deux délais supplémentaires
sont publiés tels qu'observés, avec les mêmes exigences de compétence finale,
de conservation, de ressources et de reprise. Cette petite extension ne
constitue pas une validation générale. Le total est 5 336 000 retours
d'apprentissage principaux par système, plus les copies de reprise.
