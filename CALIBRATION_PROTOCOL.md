# Calibration sans effacement : protocole fixé avant mesure

Le défaut mesuré est la surconfiance pendant les retours indépendants.
Le mode consolidé préserve la règle, mais son Brier sous bruit vaut
environ 0,37 contre 0,19 pour la banque plastique. Le but est de réduire
cette erreur sans modifier les prototypes S² ni les décisions d'admission.

## Ce qui constitue la compétence

Le programme et sa banque protégée restent ceux du mode consolidé.
Les gradients, banques candidates, contrôle, coûts neuronaux, garde
prospective et budgets de risque restent identiques. Le nouveau mode
écrit une identité distincte et un format 5 ; les modes précédents restent
restaurables avec leurs comportements.

Les déclencheurs et validations comparent explicitement la compétence
brute. Ils ne certifient pas la performance du calibrateur adaptatif.
Cela conserve la référence figée des bornes et permet de chercher une
nouvelle règle même si la calibration réduit ses erreurs apparentes.

## Calibration statistique, pas nouveaux neurones

Pour chaque contexte, le calibrateur utilise au plus les 256 derniers
retours choisis, ou la capacité de fit si elle est plus petite.
Les variables sont la probabilité brute p_i de l'action exécutée et son
résultat y_i. Aucun résultat contrefactuel des autres actions n'est donné.

La calibration commence à 32 exemples. Pour n exemples :

- b = somme(y_i) / n, taux de réussite récent appris, sans imposer 1/A ;
- D = somme((p_i - b)^2) ;
- N = somme((p_i - b)(y_i - b)) ;
- c = clip(N/D, 0,000001, 1), ou 1 si D <= 1e-12 ;
- probabilité servie q(a) = (1-c)*b + c*p(a).

C'est le minimum du Brier empirique dans cette famille de mélanges,
sous les bornes annoncées. Le Brier futur doit être mesuré séparément :
l'ajustement au passé ne le garantit pas. Le plancher positif préserve
l'ordre des actions, à la précision numérique disponible. Une réussite
argmax peut donc rester parfaite même avec des probabilités presque
uniformes ; elle ne constitue pas une preuve de bonne calibration.

b et c sont des statistiques de lecture, pas des points neuronaux
supplémentaires. Toutes les banques neuronales restent sur S².
Ce mécanisme de calibration est connu ; aucune nouveauté de paradigme
ni avantage de la courbure n'est revendiqué.

## Reprise et ressources

Le modèle conserve un cache borné des p_i et quatre sommes par contexte.
Les y_i et épisodes restent dans les buffers existants. Les sommes sont
resynchronisées toutes les 256 étapes de contexte (ou à la capacité réduite).
La restauration vérifie les caches contre chaque épisode et la banque
protégée, puis les sommes contre les observations retenues.

Une admission peut modifier routes et poids. Les probabilités des lignes
déjà observées sont alors recalculées depuis la nouvelle banque, sans
gradient supplémentaire ni utilisation de données futures.
Ces calculs statistiques supplémentaires doivent être distingués des
mises à jour neuronales. Une reprise conserve les sommes flottantes exactes.

L'import depuis le format 4 valide d'abord l'ancien modèle. Une prévision
déjà en attente reste brute jusqu'à son retour ou sa clôture ; la calibration
s'applique ensuite. La requête et le reçu répété gardent leur frontière.
Le format 3 et le mode fini suivent leurs imports explicites antérieurs.

## Essais et critères annoncés

Windows/Linux, Python 3.11, bibliothèque standard, graines 0/1/2.
16 symboles, quatre contextes, quatre actions, mêmes réglages et mêmes
actions exploratoires uniformes que le protocole de consolidation.

Comparer directement modes consolidé et calibré sur les neuf cas historiques :
bruit initial, rétention et six changements successifs, mêmes longueurs.
Publier phases, courbes, Brier et perte logarithmique de l'action exécutée,
journaux, reprises et limites. La perte logarithmique reste tronquée à
0,01 comme dans le protocole précédent ; elle doit être nommée comme telle.

Critères :

1. Après acquisition, Brier moyen des 80 000 retours bruités <= 0,205 et
   perte logarithmique tronquée <= 0,62 pour chaque graine, et tous deux
   meilleurs que la compétence protégée non calibrée.
2. Conservation argmax >= 95 % pendant le bruit ; la première mesure de
   récupération après 2 000 retours globaux (500 par contexte) retrouve
   un Brier structuré <= 0,025 dans chaque contexte.
3. Chacune des six phases de changement finit à >= 95 % dans les quatre
   contextes, les autres contextes étant préservés aux points mesurés.
4. Décisions, essais, gradients, poids et RNG de compétence identiques
   aux deux modes sur les mêmes flux, hors durée de recherche et couche
   statistique. Aucune nouvelle admission pendant le bruit.
5. Reprise JSON en validation ciblée et après renouvellement reproduisant
   1 024 retours futurs ; prévision servie égale à la valeur retournée par learn.
6. Au plus 160 points S², 16 recherches détaillées, 80 décisions, 1 024
   exemples de fit et 1 024 probabilités de cache dans cette configuration.

Ajouter trois cas à taux de bruit variables : 20 000 retours structurés,
12 000 retours indépendants à taux 0,1 pour contextes 0–1 et 0,6 pour 2–3,
puis 8 000 structurés. Les 8 000 derniers retours bruités doivent avoir
Brier <= 0,26, perte tronquée <= 0,58, meilleurs que le mode non calibré.
À la fin du bruit, |b-taux réel| <= 0,10 par contexte. La compétence et les
décisions restent comparées comme ci-dessus.

Les seuils sont des objectifs de test annoncés, pas des garanties universelles.
Les données servent à vérifier la correction ; elles ne démontrent pas
une calibration sur des applications PC, des agents qui sélectionnent
d'autres actions ou un monde à dérive arbitraire.
