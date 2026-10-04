# Conservation et validation : protocole avant exécution

Le moteur renouvelable précédent conserve les compétences seulement dans des
poids actifs, qui reçoivent les gradients du bruit. La garde d'admission ignore
ce flux de modifications. Le journal a aussi montré des validations inconclusives
malgré des gains observés positifs, sous une largeur universelle conservatrice.

## Modification déclarée

Un seul modèle admis est conservé comme banque S² protégée et sert les prévisions
structurées. La banque active et le contrôle continuent d'apprendre à chaque
retour ; les candidats sont ajustés puis figés comme auparavant.
Une admission remplace ensemble la compétence protégée et son programme.
Aucune règle cachée, indicateur de bruit ou numéro de phase n'entre dans le modèle.

Les nouveaux essais déclarent cinq horizons principaux :
128, 1 024, 4 096, 8 192, 16 384 retours. Chaque comparaison reçoit sa part du même
risque de bloc, désormais réparti sur cinq regards. La somme des blocs conserve
la borne à vie 0,05 ; un import historique depuis le moteur fini conserve 0,10.
Les essais et regards déjà utilisés gardent leurs anciennes bornes et horizons :
la frontière de politique est enregistrée, sans remboursement ni réécriture.

## Largeur conditionnelle de conservation

Le gain pour un résultat binaire est
g(y) = log clip(P_candidat(y)) - log clip(P_servi(y)).
Avec les prévisions disponibles avant y, sa largeur conditionnelle est
abs(logit(clip(p_candidat)) - logit(clip(p_servi))).

Pour une validation ciblée, les deux réseaux concernés sont figés. Avant tout
retour de validation, le moteur fixe w comme maximum de cette largeur sur
toutes les actions et les paires de routes possibles dans les autres contextes.
Il énumère une sur-approximation des affectations des prédicats : toutes les
valeurs booléennes des relations sont autorisées, même incompatibles entre elles ;
seules les égalités de contexte utilisent le vrai numéro du contexte.
Tous les slots de la capacité, même pas encore alimentés, sont inclus.
Le maximum ne peut donc omettre une future paire de routes.

La largeur universelle 2B, B=-log(0,01), reste utilisée pour la pertinence,
l'amélioration, et toute comparaison avec une banque servie plastique.
Dans la borne Hoeffding-Azuma, w/2 remplace B quand cette largeur fixe est valide.
Pour n retours fixes :
bound = (w/2) sqrt(2 log(2 famille / alpha_bloc) / n).
La garde de conservation conserve la couture temporelle uniforme annoncée :
bound = (w/2) sqrt(2 * 2^(k+1) * [log(2 famille / alpha_bloc)
    + log(pi²/6) + 2 log(k+1)]) / n, k=floor(log2(n)).
famille = 3 comparaisons * 5 regards * tentatives par bloc.

La borne concerne la moyenne des gains conditionnels prévisibles ; les épisodes
sont observés et les prévisions calculées avant leurs résultats. Le budget ne
prouve ni la pertinence du contexte choisi ni la performance future.
Un intervalle inconclusif ne devient pas une preuve de nuisance.

## Coûts et compromis à mesurer

Avec huit routes et quatre actions : la copie protège 32 points supplémentaires.
Après admission, 96 points S² sont alloués avec les banques de travail et contrôle ;
maximum 160 avec candidats, soit 192/320 degrés de liberté intrinsèques.
La mémoire protégée est bornée à une banque, pas un historique illimité de compétences.
Le journal garde au plus 16 recherches et 80 décisions par bloc par défaut.

Une compétence protégée peut garder des probabilités trop confiantes si le monde
devient aléatoire. La sonde doit donc publier aussi les Brier et pertes logarithmiques
sur les retours réellement aléatoires, en plus du succès sur l'ancienne règle.
Préserver une compétence ne prouve pas une calibration adaptée au bruit.

## Expériences et critères

Comparer RenewableLearner et ConsolidatedLearner sur les mêmes trois graines
0, 1, 2, les mêmes observations et actions, les mêmes capacités : 16 symboles,
4 contextes, 4 actions. Reprendre les mêmes flux et durées que le protocole précédent :

1. 40 000 retours aléatoires puis 40 000 retours structurés.
2. 20 000 retours structurés, 80 000 retours aléatoires puis 40 000 structurés.
3. Sept phases de 40 000 retours ; seul le contexte 0 change selon les décalages
   0 → 1 → 2 → 3 → 0 → 2 → 1. 10 000 retours par contexte par phase.

Évaluer sans apprendre, sur une copie et un flux indépendant, 512 épisodes par
contexte à chaque point ; même grille que le protocole précédent. Publier toutes
les courbes, admissions, risques, largeurs déclarées, compteurs, coûts et baisses.
Unités principales : retours globaux et retours du contexte principal.
La date d'admission et le premier point mesuré de succès sont distincts.

Exiger pour ConsolidatedLearner :
- >=95 % dans chaque contexte après bruit initial ;
- >=95 % sur l'ancienne règle à chaque frontière de bruit après acquisition ;
- >=95 % dans chaque contexte à la fin de chacune des six phases de changement ;
- aucune nouvelle admission pendant les phases de bruit indépendant ;
- reprise exacte pendant une validation ciblée et après un renouvellement ;
- mémoire bornée et tests de corruption des états, largeurs et horizons ;
- import d'une prédiction/requête en attente et apprentissage unique de son reçu.

Tester séparément un signal réel plus faible qui exige un regard au-delà de
4 096 retours. La durée des phases structurées ne sera pas changée après les
résultats pour faire disparaître un échec. Les comparaisons des deux OS utilisent
les mêmes graines : ce ne sont pas six répétitions indépendantes.

Le moteur reste un laboratoire de prédicats bornés et de poids sphériques.
Ni innovation scientifique ni avantage de courbure n'est revendiqué.
