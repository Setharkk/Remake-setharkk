# Protocole de correction de la première pièce — v2

Base : ba8f8e642f4af19620f72aaa73e719d5da6f40dd. Protocole fixé avant les mesures.

## Changements évalués
Le moteur expérimental conserve l'encodeur récurrent et les gradients intrinsèques sur S².
1. Une lecture calibrée utilise uniquement les résultats déjà reçus. Sa pente reste
positive pour préserver l'ordre des actions, sans changer les poids protégés.
2. Une révision de poids est entraînée sur le passé, puis évaluée sur des résultats
futurs face à la référence calibrée réellement servie. Une subdivision doit aussi
battre un contrôle de routage aléatoire. Les révisions ne demandent pas ce deuxième
test : une règle locale constante peut changer sans nécessiter une nouvelle partition.
3. Un adaptateur optionnel réutilise les contrats d'observation, de prévision, d'action,
de reçu, de déduplication et de travail coopératif. Le moteur format 8 reste le défaut.

## Critères mesurés
Trois graines (0, 1, 2), mêmes observations, actions aléatoires et résultats pour les
variantes v1 et v2 : 2 048 résultats de bruit, 16 384 de signal, 8 192 de bruit,
4 096 de reprise. Le signal distingue les suffixes AAB/ABB avec présence, premiers
ordres, longueur et contextes appariés. Évaluations sans apprentissage : 512 épisodes,
préfixes ordinaires, préfixes longs, nouveau contexte.

* Bruit après acquisition : Brier préquentiel v2 ≤ 0,28 sur toute la phase,
  ≤ 0,27 sur sa seconde moitié ; aucune admission de subdivision ou de révision.
* Politique conservée après bruit : exactitude ≥ 95 % dans les trois évaluations.
* Reprise : exactitude ≥ 95 %, Brier d'évaluation ≤ 0,02.
* Changement de règle : six inversions successives, 32 768 résultats par inversion,
  exactitude finale ≥ 95 % à chaque inversion et au moins une révision de poids.
  Le budget d'exposition est déclaré ; une acquisition tardive est mesurée.
* Ingénierie : tests Windows/Linux, probabilités et checkpoints identiques en calcul
  direct et coopératif, reprise JSON des phases de partition et de replay, reçus
  dupliqués sans nouvel apprentissage, exception privée récupérable, checkpoints
  invalides rejetés. Quota respecté en unités de travail.

Les résultats de recherche négatifs sont conservés, sans modifier ces seuils pour
les rendre positifs. Ils empêchent de présenter le prototype comme un remplacement
validé du service courant.

## Budgets et portée
Deux actions binaires, huit contextes, 64 symboles, huit feuilles, profondeur quatre.
Fenêtre de replay ≤ 256, historique de calibration ≤ 256 résultats par contexte.
Une unité calcule un bloc d'au plus huit lignes (16 distances ou 8 logarithmes), un gradient, ou une
opération administrative bornée. Initialisation, shuffle, calibration et publication
restent des opérations atomiques bornées ; le quota ne garantit pas une latence réelle.

La famille d'opérateurs reste fournie : partition binaire géodésique et révision de
poids. Pas de suppression/fusion automatique de feuilles ni de résolution générale
des tâches. L'espace S² et les contrôles ne démontrent pas une nouveauté de paradigme
ni une supériorité de la courbure. Les contextes distincts disposent d'une calibration
distincte, mais pas automatiquement de poids indépendants.

## Versionnement
Le prototype v1 reste une référence expérimentale reproductible. Le v2 dispose de
sa propre identité et de checkpoints ; un checkpoint format 8 ne peut pas être
converti en trace récurrente sans inventer l'ordre absent des données. Le contrat
extérieur peut rester commun sans prétendre que les représentations sont identiques.
