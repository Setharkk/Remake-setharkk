# Protocole : catalogue d'actions configurable sur S²

Base : 32a5ba2976a3955c576e9a3a0508ab92e9d44ae8. Critères fixés avant mesure.

## Extension
Le nouveau backend garde les sorties Bernoulli et la partition géodésique binaire.
Le nombre de sorties N est indépendant du nombre de branches et du résultat 0/1.
Aucun plafond 16 n'est imposé : le constructeur contrôle avant allocation un budget
de points S² et un budget de lignes retenues. Le catalogue reste fixe pendant la
vie du modèle ; une action paramétrée ou la création spontanée d'actions est hors
de cette extension.

Budgets par défaut : 65 536 points, 131 072 lignes conservées estimées.
Réserve de points : N(8L+2)+2L pour L feuilles maximales.
Réserve de lignes : (L+3)W+4TC pour fenêtre W, T contextes, calibration C.
Les copies de checkpoint, l'objet Python et la mémoire de l'exécuteur ne sont pas
des octets garantis par ces réserves ; les snapshots et temps sont mesurés.

Par défaut W=128N, minimum de fit=64N, C=256.
Les horizons sont (128,512,2048,8192)*ceil(N/2).
Le seuil de déclenchement Brier est 0,18*2/N ; le gain minimum est 0,01*2/N.
Les poids neuronaux et mises à jour demeurent intrinsèques sur S².

## Validation statistique
Avant chaque label, les deux gains possibles de log-probabilité tronquée sont
calculés. Leur largeur w est connue après l'action et avant le résultat.
Pour chacune des deux comparaisons, on accumule V=Σw². Le rayon est
min_λ [log(4*K*4*16/α)/λ + λV/8]/n, avec K comparaisons et la grille de
16 valeurs λ=2^k/64, k=-4..11 déclarées. Cette grille évite de choisir après mesure
un paramètre libre sans en payer le risque. α_j=0,05/[j(j+1)] reste cumulatif.
Les calibrations utilisent uniquement les labels antérieurs à chaque prévision.
Une révision demande aussi des assertions sélectionnées sur le passé :
sortie candidate ≥0,75 ou ≤0,25, déplacée d'au moins 0,05. Cela couvre
les changements de règle et le renforcement de poids encore peu confiants. Les résultats futurs de ces actions doivent
confirmer un taux >0,6 ou <0,4 avec une borne de Hoeffding et allocation du risque
aux actions/horizons. Cette condition distingue une règle nouvelle d'une simple
réduction de confiance sous bruit. Une importation d'un essai v2 en cours garde
sa politique précédente jusqu'à clôture.

## Expériences
Trois graines 0,1,2, N=4,8,32 :
2 048 résultats de bruit initial, 32 768 de signal, 16 384 de bruit,
8 192 de reprise, puis 65 536 d'inversion.
Observations identiques AAB/ABB à préfixes variables et contextes équilibrés.
Actions et bruit aléatoires externes partagés entre les scénarios.

Deux familles :
* Toutes les actions pertinentes : réussite selon la parité de l'action et l'état.
* Récompenses rares : une seule action correcte par état, identités 0 et N−1 ;
  les autres actions échouent. Ce scénario vérifie que les seuils moyens ne rendent
  pas le catalogue large incapable d'apprendre.

Critères : exactitude de la politique ≥95 % en fin de signal, après bruit,
après reprise et après inversion ; Brier après reprise ≤0,02 ; Brier sous bruit
≤0,29, seconde moitié ≤0,27 ; aucune admission pendant les phases de bruit.
La vitesse est relevée à 2 048,8 192,16 384,32 768 pendant le signal, puis
8 192,32 768,65 536 après inversion. Un résultat négatif est publié sans déplacer
les seuils.

## Ingénierie
Windows/Linux : suite existante, prévisions et checkpoints exacts direct/service
pour 4,8,32 actions ; pauses JSON de partition et replay ; action N−1 correctement
apprise ; doublons sans second gradient ; budgets dépassés rejetés avant allocation.
Construction, prévision et checkpoint à 128 actions, sans revendiquer leur apprentissage.
Imports v2 : prévision, requête, reçu et essai en cours conservés ; reprise des fits
en cours vérifiée. Les budgets et le nombre d'actions sont validés à la restauration.

Les expériences ne prouvent pas la capacité de tâches générales, l'intérêt de S²,
ou un catalogue infini. Le temps par prévision et l'exploration augmentent avec N.

## Correction après la première campagne

Les critères, graines, observations et nombres de résultats ci-dessus restent
inchangés. Le premier candidat a montré un filtre de révision incapable de
renforcer une compétence correcte mais peu confiante, et une calibration trop
lente lorsqu'elle était dimensionnée comme les exemples par action.
Le filtre sélectionne maintenant des assertions de résultat (pas seulement des
inversions de signe) et leur confirmation future reste obligatoire. La fenêtre
du calibrateur scalaire à quatre sommes vaut 256, indépendamment de N ;
les fenêtres d'exemples neuronaux restent proportionnelles à N.
La campagne initiale négative est conservée avec ses résultats bruts.

La deuxième mesure a isolé deux autres verrous : un déclencheur Brier agrégé
peut empêcher un raffinement de confiance pourtant utile, et un essai de
partition devenu dépassé peut monopoliser l'unique validation.
Une révision sélectionnée depuis les labels passés n'est donc plus conditionnée
au déclencheur de nouvelle structure. Tous les 128 labels pertinents, un essai
de partition est retiré si une révision des poids protégés devient nécessaire.
Ce retrait n'admet rien et ne rend aucun risque ; le candidat suivant devra
encore passer ses contrôles futurs. Les critères d'expérience restent inchangés.

La troisième mesure a montré des candidats de révision contradits par leurs
labels futurs, mais encore retenus à cause d'un gain moyen positif sur d'autres
actions. Une borne opposée à une assertion clôt maintenant l'essai, sans
admission ni remboursement du risque. Avant toute admission de révision,
les labels récents doivent aussi garder la direction sélectionnée. Ce contrôle
supplémentaire peut seulement refuser une admission ; il ne remplace pas la
borne prospective. Un essai v2 importé garde ses règles jusqu'à clôture.

La quatrième mesure a isolé un défaut d'ordonnancement : le raffinement d'une
feuille déjà correcte peut retarder le changement de règle d'une autre feuille.
Les contradictions fortes de la compétence protégée passent maintenant avant
les raffinements de confiance. Un raffinement est retiré si une autre feuille
présente une inversion, sauf si l'essai actif traite déjà une inversion.
Le risque n'est jamais remboursé. Cette priorité utilise les labels passés
et les probabilités protégées, sans connaître la phase ou la règle du laboratoire.
